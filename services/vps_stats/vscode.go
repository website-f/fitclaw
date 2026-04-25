package main

import (
	"context"
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"

	"github.com/shirou/gopsutil/v4/process"
)

// vscodeWindow describes one VS Code window we believe is open, identified
// by its workspace folder. We dedupe by workspace path because a single
// window has 5–10 helper processes and we only want one row per project.
type vscodeWindow struct {
	WorkspacePath string `json:"workspace_path"`
	ProjectName   string `json:"project_name"`
	PID           int32  `json:"pid"`
	Cmdline       string `json:"cmdline,omitempty"`
}

// claudeSession describes one recently-active Claude Code session found
// in ~/.claude/projects/<encoded-cwd>/sessions/*.jsonl.
type claudeSession struct {
	SessionID    string `json:"session_id"`
	ProjectPath  string `json:"project_path"`
	ProjectName  string `json:"project_name"`
	UpdatedAt    string `json:"updated_at"`
	UpdatedAgoMS int64  `json:"updated_ago_ms"`
	LastUserMsg  string `json:"last_user_msg,omitempty"`
}

func handleVSCode(w http.ResponseWriter, r *http.Request) {
	rows, err := collectVSCodeWindows(r.Context())
	if err != nil {
		http.Error(w, "failed to collect vscode windows", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(rows)
}

func handleClaudeSessions(w http.ResponseWriter, r *http.Request) {
	limit := 20
	rows, err := collectClaudeSessions(limit)
	if err != nil {
		http.Error(w, "failed to collect claude sessions", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(rows)
}

func isVSCodeProcessName(name string) bool {
	low := strings.ToLower(name)
	switch low {
	case "code", "code.exe", "code-insiders", "code-insiders.exe":
		return true
	}
	// Some packagings show as "Visual Studio Code" — be lenient.
	return strings.Contains(low, "code") &&
		(strings.HasSuffix(low, ".exe") || runtime.GOOS != "windows") &&
		!strings.Contains(low, "vscode-server-fork") // exclude helpers
}

// extractWorkspaceFromArgs walks command-line args, returning the first one
// that exists on disk and is a directory. VS Code launched as `code <path>`
// passes the workspace path as a positional arg.
func extractWorkspaceFromArgs(args []string) string {
	for _, raw := range args {
		clean := strings.Trim(strings.TrimSpace(raw), "\"'")
		if clean == "" || strings.HasPrefix(clean, "-") {
			continue
		}
		if info, err := os.Stat(clean); err == nil && info.IsDir() {
			abs, err := filepath.Abs(clean)
			if err == nil {
				return abs
			}
			return clean
		}
	}
	return ""
}

func collectVSCodeWindows(ctx context.Context) ([]vscodeWindow, error) {
	procs, err := process.ProcessesWithContext(ctx)
	if err != nil {
		return nil, err
	}

	seen := make(map[string]vscodeWindow)
	for _, p := range procs {
		name, _ := p.NameWithContext(ctx)
		if !isVSCodeProcessName(name) {
			continue
		}
		args, _ := p.CmdlineSliceWithContext(ctx)
		ws := extractWorkspaceFromArgs(args)
		// Fallback: cwd of the process — usually where `code .` was run.
		if ws == "" {
			if cwd, err := p.CwdWithContext(ctx); err == nil && cwd != "" {
				if info, err := os.Stat(cwd); err == nil && info.IsDir() {
					ws = cwd
				}
			}
		}
		if ws == "" {
			continue
		}
		// Normalize to canonical path so the dedup key is stable.
		clean := filepath.Clean(ws)
		if _, ok := seen[clean]; ok {
			continue
		}
		cmdline, _ := p.CmdlineWithContext(ctx)
		seen[clean] = vscodeWindow{
			WorkspacePath: clean,
			ProjectName:   filepath.Base(clean),
			PID:           p.Pid,
			Cmdline:       cmdline,
		}
	}

	out := make([]vscodeWindow, 0, len(seen))
	for _, v := range seen {
		out = append(out, v)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].ProjectName < out[j].ProjectName })
	return out, nil
}

func claudeProjectsRoot() string {
	if v := os.Getenv("CLAUDE_HOME"); v != "" {
		return filepath.Join(v, "projects")
	}
	home, err := os.UserHomeDir()
	if err != nil || home == "" {
		return ""
	}
	return filepath.Join(home, ".claude", "projects")
}

// decodeProjectDirName reverses Claude Code's project-dir encoding. The
// encoding is fairly simple: replace `/` with `-`. e.g. for cwd
// `/c/Users/admin/Desktop/foo`, the dir is `-c-Users-admin-Desktop-foo`.
// We recover the original path by replacing the leading dash with `/` and
// every other dash with `/`. On Windows, also restore the drive letter.
func decodeProjectDirName(name string) string {
	if name == "" {
		return ""
	}
	if strings.HasPrefix(name, "-") {
		path := "/" + strings.ReplaceAll(strings.TrimPrefix(name, "-"), "-", "/")
		// Heuristic for Windows: if first component is a single letter, treat
		// as a drive letter — `/c/Users/...` becomes `c:/Users/...`.
		parts := strings.Split(strings.TrimPrefix(path, "/"), "/")
		if len(parts) > 0 && len(parts[0]) == 1 {
			return parts[0] + ":/" + strings.Join(parts[1:], "/")
		}
		return path
	}
	return strings.ReplaceAll(name, "-", "/")
}

func collectClaudeSessions(limit int) ([]claudeSession, error) {
	root := claudeProjectsRoot()
	if root == "" {
		return nil, nil
	}
	if _, err := os.Stat(root); err != nil {
		return nil, nil
	}

	type fileEntry struct {
		path      string
		size      int64
		modUnixMS int64
		project   string
	}

	var files []fileEntry

	projects, err := os.ReadDir(root)
	if err != nil {
		return nil, err
	}
	for _, proj := range projects {
		if !proj.IsDir() {
			continue
		}
		projectPath := decodeProjectDirName(proj.Name())
		// Claude stores transcripts directly under the project dir as <session>.jsonl
		// (older layouts may use a "sessions" subdir).
		candidates := []string{
			filepath.Join(root, proj.Name()),
			filepath.Join(root, proj.Name(), "sessions"),
		}
		for _, dir := range candidates {
			entries, err := os.ReadDir(dir)
			if err != nil {
				continue
			}
			for _, e := range entries {
				if e.IsDir() {
					continue
				}
				if !strings.HasSuffix(e.Name(), ".jsonl") {
					continue
				}
				info, err := e.Info()
				if err != nil {
					continue
				}
				files = append(files, fileEntry{
					path:      filepath.Join(dir, e.Name()),
					size:      info.Size(),
					modUnixMS: info.ModTime().UnixMilli(),
					project:   projectPath,
				})
			}
		}
	}

	sort.Slice(files, func(i, j int) bool { return files[i].modUnixMS > files[j].modUnixMS })
	if limit > 0 && len(files) > limit {
		files = files[:limit]
	}

	now := unixMillisNow()
	out := make([]claudeSession, 0, len(files))
	for _, f := range files {
		sessID := strings.TrimSuffix(filepath.Base(f.path), ".jsonl")
		lastUser := lastUserTextFromTranscript(f.path)
		out = append(out, claudeSession{
			SessionID:    sessID,
			ProjectPath:  f.project,
			ProjectName:  filepath.Base(f.project),
			UpdatedAt:    formatUnixMS(f.modUnixMS),
			UpdatedAgoMS: now - f.modUnixMS,
			LastUserMsg:  lastUser,
		})
	}
	return out, nil
}

func lastUserTextFromTranscript(path string) string {
	const maxLen = 200
	f, err := os.Open(path)
	if err != nil {
		return ""
	}
	defer f.Close()

	// Read the whole file (transcripts are typically under ~1 MB; if larger,
	// callers should use a streamed reverse parser — fine for now).
	buf, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	var last string
	for _, line := range strings.Split(string(buf), "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		var entry map[string]any
		if err := json.Unmarshal([]byte(line), &entry); err != nil {
			continue
		}
		message, _ := entry["message"].(map[string]any)
		role, _ := message["role"].(string)
		if role == "" {
			role, _ = entry["role"].(string)
		}
		if role != "user" {
			continue
		}
		content, ok := message["content"]
		if !ok {
			content = entry["content"]
		}
		text := stringifyContent(content)
		if text == "" || strings.HasPrefix(text, "<") {
			continue
		}
		last = text
	}
	if len(last) > maxLen {
		last = last[:maxLen] + "…"
	}
	return last
}

func stringifyContent(content any) string {
	switch v := content.(type) {
	case string:
		return v
	case []any:
		var parts []string
		for _, item := range v {
			block, ok := item.(map[string]any)
			if !ok {
				continue
			}
			if t, _ := block["type"].(string); t == "text" {
				if text, ok := block["text"].(string); ok {
					parts = append(parts, text)
				}
			}
		}
		return strings.Join(parts, "\n")
	}
	return ""
}
