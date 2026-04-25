package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"sort"
	"strings"
)

var (
	defaultServerURL = strings.TrimRight(getenv("MEMORYCORE_SERVER_URL", "http://localhost:8000"), "/")
	defaultUserID    = getenv("MEMORYCORE_USER_ID", "fitclaw")
	skipDirs         = map[string]bool{
		".git": true, ".idea": true, ".vscode": true, ".venv": true, "venv": true, "__pycache__": true,
		"node_modules": true, "dist": true, "build": true, ".next": true, ".nuxt": true, ".mypy_cache": true,
		".pytest_cache": true, ".gradle": true, "Pods": true, "build-output": true, "data": true,
	}
	importantFileNames = []string{
		"README.md", "README.txt", "package.json", "pyproject.toml", "requirements.txt", "Dockerfile",
		"docker-compose.yml", "docker-compose.yaml", ".env.example", "Makefile",
	}
)

type config struct {
	ServerURL    string
	UserID       string
	Path         string
	ProjectKey   string
	Output       string
	NoWriteLocal bool
}

type projectSummary struct {
	ProjectKey string `json:"project_key"`
	Title      string `json:"title"`
	Summary    string `json:"summary"`
	UpdatedAt  string `json:"updated_at"`
}

type profileResponse struct {
	UserID              string   `json:"user_id"`
	DisplayName         string   `json:"display_name"`
	About               string   `json:"about"`
	Preferences         []string `json:"preferences"`
	CodingPreferences   []string `json:"coding_preferences"`
	WorkflowPreferences []string `json:"workflow_preferences"`
	Notes               []string `json:"notes"`
	Tags                []string `json:"tags"`
}

type projectPayload struct {
	Title          string   `json:"title,omitempty"`
	Summary        string   `json:"summary,omitempty"`
	RootHint       string   `json:"root_hint,omitempty"`
	RepoOrigin     string   `json:"repo_origin,omitempty"`
	Stack          []string `json:"stack,omitempty"`
	Goals          []string `json:"goals,omitempty"`
	ImportantFiles []string `json:"important_files,omitempty"`
	Commands       []string `json:"commands,omitempty"`
	Structure      []string `json:"structure,omitempty"`
	Preferences    []string `json:"preferences,omitempty"`
	Notes          []string `json:"notes,omitempty"`
	Tags           []string `json:"tags,omitempty"`
}

type saveResult struct {
	ProjectKey string `json:"project_key"`
}

func main() {
	cfg, remaining, err := parseArgs(os.Args[1:])
	if err != nil {
		fail(err)
	}
	if len(remaining) == 0 {
		fail(errors.New("usage: memorycore {usage|design|<natural language>}"))
	}
	switch remaining[0] {
	case "usage":
		if err := runUsageCommand(cfg, remaining[1:]); err != nil {
			fail(err)
		}
	case "design":
		if err := runDesignCommand(cfg, remaining[1:]); err != nil {
			fail(err)
		}
	default:
		phrase := strings.Join(remaining, " ")
		if strings.TrimSpace(phrase) == "" {
			fail(errors.New("usage: memorycore remember this whole thing"))
		}
		if err := runNatural(cfg, phrase); err != nil {
			fail(err)
		}
	}
}

func parseArgs(args []string) (config, []string, error) {
	cfg := config{
		ServerURL: defaultServerURL,
		UserID:    defaultUserID,
		Path:      ".",
	}
	var remaining []string
	for index := 0; index < len(args); index++ {
		token := args[index]
		switch token {
		case "--server-url":
			index++
			if index >= len(args) {
				return cfg, nil, errors.New("--server-url requires a value")
			}
			cfg.ServerURL = strings.TrimRight(args[index], "/")
		case "--user-id":
			index++
			if index >= len(args) {
				return cfg, nil, errors.New("--user-id requires a value")
			}
			cfg.UserID = args[index]
		case "--path":
			index++
			if index >= len(args) {
				return cfg, nil, errors.New("--path requires a value")
			}
			cfg.Path = args[index]
		case "--project-key":
			index++
			if index >= len(args) {
				return cfg, nil, errors.New("--project-key requires a value")
			}
			cfg.ProjectKey = args[index]
		case "--output":
			index++
			if index >= len(args) {
				return cfg, nil, errors.New("--output requires a value")
			}
			cfg.Output = args[index]
		case "--no-write-local":
			cfg.NoWriteLocal = true
		default:
			remaining = append(remaining, token)
		}
	}
	return cfg, remaining, nil
}

func runNatural(cfg config, phrase string) error {
	normalized := normalizePhrase(phrase)
	lowered := strings.ToLower(normalized)
	projectKey := cfg.ProjectKey
	if strings.TrimSpace(projectKey) == "" {
		projectKey = slugify(filepath.Base(resolvePath(cfg.Path)))
	}

	switch {
	case containsAny(lowered, "clear all memory", "forget everything", "wipe memorycore", "wipe all memory"):
		return clearAll(cfg)
	case containsAny(lowered, "list my projects", "list projects", "show my projects", "show my memories", "list my memories"):
		return listProjects(cfg)
	case containsAny(lowered, "show this project memory", "view this project memory", "show this memory", "open this memory"):
		return showProject(cfg, projectKey)
	case containsAny(lowered, "pull this project memory", "pull this memory", "pull this project", "restore this project memory"):
		return pullProject(cfg, projectKey)
	case containsAny(lowered, "forget this project", "delete this project memory", "remove this project memory", "forget this memory"):
		return deleteProject(cfg, projectKey)
	case containsAny(lowered, "remember this whole thing", "remember this project", "save this project memory", "save this whole project", "remember everything in this project"):
		return saveProject(cfg, projectKey, normalized)
	}

	if preference := extractPreference(normalized); preference != "" {
		return rememberPreference(cfg, preference)
	}
	if containsAny(lowered, "list my profile", "show my profile", "show my preferences") {
		return showProfile(cfg)
	}
	if containsAny(lowered, "forget my profile", "clear my profile") {
		return clearProfile(cfg)
	}
	if strings.Contains(lowered, "remember") {
		return saveProject(cfg, projectKey, normalized)
	}

	return errors.New("I could not map that MemoryCore instruction yet. Try: jarvis remember this whole thing")
}

func listProjects(cfg config) error {
	var projects []projectSummary
	if err := requestJSON(http.MethodGet, cfg.ServerURL, "/api/v1/memorycore/projects", map[string]string{"user_id": cfg.UserID}, nil, &projects); err != nil {
		return err
	}
	if len(projects) == 0 {
		fmt.Println("No MemoryCore projects stored yet.")
		return nil
	}
	for _, item := range projects {
		fmt.Printf("- %s: %s (%s)\n", item.ProjectKey, item.Title, item.UpdatedAt)
	}
	return nil
}

func saveProject(cfg config, projectKey string, note string) error {
	root := resolvePath(cfg.Path)
	payload := buildProjectPayload(root, projectKey, note)
	var result saveResult
	if err := requestJSON(http.MethodPut, cfg.ServerURL, "/api/v1/memorycore/projects/"+url.PathEscape(projectKey), map[string]string{"user_id": cfg.UserID}, payload, &result); err != nil {
		return err
	}
	fmt.Printf("Saved project memory `%s` to %s.\n", result.ProjectKey, cfg.ServerURL)

	if cfg.NoWriteLocal {
		return nil
	}
	markdown, err := requestText(cfg.ServerURL, "/api/v1/memorycore/projects/"+url.PathEscape(projectKey)+"/markdown", map[string]string{"user_id": cfg.UserID})
	if err != nil {
		return err
	}
	output := cfg.Output
	if strings.TrimSpace(output) == "" {
		output = filepath.Join(root, "MEMORYCORE.md")
	}
	if err := os.WriteFile(output, []byte(markdown), 0o644); err != nil {
		return err
	}
	fmt.Printf("Wrote local MemoryCore file to %s\n", output)
	return nil
}

func pullProject(cfg config, projectKey string) error {
	markdown, err := requestText(cfg.ServerURL, "/api/v1/memorycore/projects/"+url.PathEscape(projectKey)+"/markdown", map[string]string{"user_id": cfg.UserID})
	if err != nil {
		return err
	}
	output := cfg.Output
	if strings.TrimSpace(output) == "" {
		output = filepath.Join(resolvePath(cfg.Path), "MEMORYCORE.md")
	}
	if err := os.WriteFile(output, []byte(markdown), 0o644); err != nil {
		return err
	}
	fmt.Printf("Wrote MemoryCore file to %s\n", output)
	return nil
}

func showProject(cfg config, projectKey string) error {
	markdown, err := requestText(cfg.ServerURL, "/api/v1/memorycore/projects/"+url.PathEscape(projectKey)+"/markdown", map[string]string{"user_id": cfg.UserID})
	if err != nil {
		return err
	}
	fmt.Print(strings.TrimSpace(markdown))
	fmt.Println()
	return nil
}

func deleteProject(cfg config, projectKey string) error {
	var result map[string]any
	if err := requestJSON(http.MethodDelete, cfg.ServerURL, "/api/v1/memorycore/projects/"+url.PathEscape(projectKey), map[string]string{"user_id": cfg.UserID}, nil, &result); err != nil {
		return err
	}
	if deleted, _ := result["deleted"].(bool); deleted {
		fmt.Printf("Deleted project memory `%s`.\n", projectKey)
	} else {
		fmt.Println("No matching project memory was found.")
	}
	return nil
}

func clearAll(cfg config) error {
	var result map[string]any
	if err := requestJSON(http.MethodDelete, cfg.ServerURL, "/api/v1/memorycore/", map[string]string{"user_id": cfg.UserID}, nil, &result); err != nil {
		return err
	}
	fmt.Printf("Cleared MemoryCore. Deleted profile: %v, deleted projects: %v.\n", result["deleted_profile"], result["deleted_projects"])
	return nil
}

func rememberPreference(cfg config, preference string) error {
	profile, err := getOptionalProfile(cfg)
	if err != nil {
		return err
	}
	if profile == nil {
		profile = &profileResponse{}
	}
	profile.Preferences = appendUnique(profile.Preferences, preference)
	body := map[string]any{
		"display_name":         blankToNil(profile.DisplayName),
		"about":                blankToNil(profile.About),
		"preferences":          profile.Preferences,
		"coding_preferences":   profile.CodingPreferences,
		"workflow_preferences": profile.WorkflowPreferences,
		"notes":                profile.Notes,
		"tags":                 profile.Tags,
	}
	var updated profileResponse
	if err := requestJSON(http.MethodPut, cfg.ServerURL, "/api/v1/memorycore/profile", map[string]string{"user_id": cfg.UserID}, body, &updated); err != nil {
		return err
	}
	fmt.Printf("Saved MemoryCore preference for %s.\n", updated.UserID)
	return nil
}

func showProfile(cfg config) error {
	profile, err := getOptionalProfile(cfg)
	if err != nil {
		return err
	}
	if profile == nil {
		fmt.Println("No MemoryCore profile stored yet.")
		return nil
	}
	raw, err := json.MarshalIndent(profile, "", "  ")
	if err != nil {
		return err
	}
	fmt.Println(string(raw))
	return nil
}

func clearProfile(cfg config) error {
	var result map[string]any
	if err := requestJSON(http.MethodDelete, cfg.ServerURL, "/api/v1/memorycore/profile", map[string]string{"user_id": cfg.UserID}, nil, &result); err != nil {
		return err
	}
	if deleted, _ := result["deleted"].(bool); deleted {
		fmt.Println("Deleted MemoryCore profile.")
	} else {
		fmt.Println("No MemoryCore profile was stored.")
	}
	return nil
}

func getOptionalProfile(cfg config) (*profileResponse, error) {
	u := cfg.ServerURL + "/api/v1/memorycore/profile?" + url.Values{"user_id": []string{cfg.UserID}}.Encode()
	req, err := http.NewRequest(http.MethodGet, u, nil)
	if err != nil {
		return nil, err
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusNotFound {
		return nil, nil
	}
	if resp.StatusCode >= 300 {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("MemoryCore request failed (%d): %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}
	var profile profileResponse
	if err := json.NewDecoder(resp.Body).Decode(&profile); err != nil {
		return nil, err
	}
	return &profile, nil
}

func requestJSON(method, serverURL, path string, query map[string]string, body any, out any) error {
	u := buildURL(serverURL, path, query)
	var reader io.Reader
	if body != nil {
		payload, err := json.Marshal(body)
		if err != nil {
			return err
		}
		reader = bytes.NewReader(payload)
	}
	req, err := http.NewRequest(method, u, reader)
	if err != nil {
		return err
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		bodyBytes, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("MemoryCore request failed (%d): %s", resp.StatusCode, strings.TrimSpace(string(bodyBytes)))
	}
	if out == nil {
		return nil
	}
	return json.NewDecoder(resp.Body).Decode(out)
}

func requestText(serverURL, path string, query map[string]string) (string, error) {
	u := buildURL(serverURL, path, query)
	req, err := http.NewRequest(http.MethodGet, u, nil)
	if err != nil {
		return "", err
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	bodyBytes, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 300 {
		return "", fmt.Errorf("MemoryCore request failed (%d): %s", resp.StatusCode, strings.TrimSpace(string(bodyBytes)))
	}
	return string(bodyBytes), nil
}

func buildURL(serverURL, path string, query map[string]string) string {
	values := url.Values{}
	for key, value := range query {
		values.Set(key, value)
	}
	return strings.TrimRight(serverURL, "/") + path + "?" + values.Encode()
}

func buildProjectPayload(root, projectKey, note string) projectPayload {
	dirs, files := collectStructure(root, 24, 40)
	summary := firstReadmeSummary(root)
	if summary == "" {
		summary = fmt.Sprintf("Memory snapshot for %s.", filepath.Base(root))
	}
	payload := projectPayload{
		Title:          titleFromProjectKey(projectKey, root),
		Summary:        summary,
		RootHint:       root,
		RepoOrigin:     gitOrigin(root),
		Stack:          detectStack(root, files),
		ImportantFiles: importantFiles(files),
		Commands:       detectCommands(root),
		Structure:      uniqueStrings(append(dirs, take(files, 20)...)),
	}
	if strings.TrimSpace(note) != "" {
		payload.Notes = []string{fmt.Sprintf("Saved via natural command: %s", note)}
	}
	return payload
}

func firstReadmeSummary(root string) string {
	for _, name := range []string{"README.md", "README.txt", "README"} {
		path := filepath.Join(root, name)
		data, err := os.ReadFile(path)
		if err != nil {
			continue
		}
		blocks := strings.Split(strings.ReplaceAll(string(data), "\r\n", "\n"), "\n\n")
		for _, block := range blocks {
			lines := strings.Split(block, "\n")
			var current []string
			for _, line := range lines {
				trimmed := strings.TrimSpace(line)
				if trimmed == "" || strings.HasPrefix(trimmed, "#") {
					continue
				}
				current = append(current, trimmed)
			}
			if len(current) > 0 {
				text := strings.Join(current, " ")
				if len(text) > 500 {
					return text[:500]
				}
				return text
			}
		}
	}
	return ""
}

func collectStructure(root string, maxDirs, maxFiles int) ([]string, []string) {
	var dirs []string
	var files []string
	_ = filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return nil
		}
		name := d.Name()
		if d.IsDir() && skipDirs[name] && path != root {
			return filepath.SkipDir
		}

		rel, err := filepath.Rel(root, path)
		if err != nil || rel == "." {
			return nil
		}
		rel = filepath.ToSlash(rel)
		depth := len(strings.Split(rel, "/"))
		if d.IsDir() {
			if depth > 2 {
				return filepath.SkipDir
			}
			if len(dirs) < maxDirs {
				dirs = appendIfMissing(dirs, rel+"/")
			}
			return nil
		}
		if depth > 3 || strings.HasPrefix(name, ".memorycore-") || strings.HasPrefix(name, "=") {
			return nil
		}
		lower := strings.ToLower(name)
		if strings.HasSuffix(lower, ".pyc") || strings.HasSuffix(lower, ".pyo") || strings.HasSuffix(lower, ".pyd") || strings.HasSuffix(lower, ".db") {
			return nil
		}
		if len(files) < maxFiles {
			files = appendIfMissing(files, rel)
		}
		return nil
	})
	sort.Strings(dirs)
	sort.Strings(files)
	return dirs, files
}

func importantFiles(files []string) []string {
	fileSet := map[string]string{}
	for _, file := range files {
		fileSet[strings.ToLower(file)] = file
	}
	var result []string
	for _, item := range importantFileNames {
		if match, ok := fileSet[strings.ToLower(item)]; ok {
			result = append(result, match)
		}
	}
	if contains(files, "app/main.py") {
		result = append(result, "app/main.py")
	}
	if contains(files, "app/services/message_service.py") {
		result = append(result, "app/services/message_service.py")
	}
	return uniqueStrings(result)
}

func detectStack(root string, files []string) []string {
	joined := strings.ToLower(strings.Join(files, "\n"))
	var stack []string
	if strings.Contains(joined, "package.json") {
		stack = append(stack, "Node.js / npm")
	}
	if strings.Contains(joined, "pyproject.toml") || strings.Contains(joined, "requirements.txt") {
		stack = append(stack, "Python")
	}
	if strings.Contains(joined, "dockerfile") {
		stack = append(stack, "Docker")
	}
	if strings.Contains(joined, "docker-compose.yml") || strings.Contains(joined, "docker-compose.yaml") {
		stack = append(stack, "Docker Compose")
	}
	if data, err := os.ReadFile(filepath.Join(root, "requirements.txt")); err == nil && strings.Contains(strings.ToLower(string(data)), "fastapi") {
		stack = append(stack, "FastAPI")
	}
	for _, file := range files {
		if strings.HasSuffix(file, ".tsx") || strings.HasSuffix(file, ".jsx") {
			stack = append(stack, "React-style frontend")
			break
		}
	}
	for _, file := range files {
		if strings.Contains(strings.ToLower(file), "capacitor") {
			stack = append(stack, "Capacitor mobile wrapper")
			break
		}
	}
	return uniqueStrings(stack)
}

func detectCommands(root string) []string {
	var commands []string
	if data, err := os.ReadFile(filepath.Join(root, "package.json")); err == nil {
		var payload map[string]any
		if json.Unmarshal(data, &payload) == nil {
			if scripts, ok := payload["scripts"].(map[string]any); ok {
				var names []string
				for key := range scripts {
					names = append(names, key)
				}
				sort.Strings(names)
				for _, name := range take(names, 8) {
					commands = append(commands, "npm run "+name)
				}
			}
		}
	}
	if fileExists(filepath.Join(root, "docker-compose.yml")) || fileExists(filepath.Join(root, "docker-compose.yaml")) {
		commands = append(commands, "docker compose up -d")
	}
	if fileExists(filepath.Join(root, "requirements.txt")) {
		commands = append(commands, "python -m compileall app")
	}
	if fileExists(filepath.Join(root, "Makefile")) {
		commands = append(commands, "make")
	}
	return uniqueStrings(commands)
}

func gitOrigin(root string) string {
	cmd := exec.Command("git", "-C", root, "remote", "get-url", "origin")
	data, err := cmd.Output()
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(data))
}

func normalizePhrase(text string) string {
	normalized := strings.Join(strings.Fields(strings.TrimSpace(text)), " ")
	re := regexp.MustCompile(`(?i)^\s*hey\s+[\w-]+[,\s:;-]*`)
	return strings.TrimSpace(re.ReplaceAllString(normalized, ""))
}

func extractPreference(text string) string {
	patterns := []string{
		`(?i)remember (?:that )?i prefer (?P<value>.+)`,
		`(?i)remember this preference[:\s]+(?P<value>.+)`,
		`(?i)my preference is (?P<value>.+)`,
	}
	for _, pattern := range patterns {
		re := regexp.MustCompile(pattern)
		match := re.FindStringSubmatch(text)
		if len(match) == 0 {
			continue
		}
		valueIndex := re.SubexpIndex("value")
		if valueIndex <= 0 || valueIndex >= len(match) {
			continue
		}
		value := strings.TrimSpace(strings.Trim(match[valueIndex], " ."))
		if value != "" {
			return strings.ToUpper(value[:1]) + value[1:]
		}
	}
	return ""
}

func slugify(value string) string {
	re := regexp.MustCompile(`[^a-z0-9]+`)
	slug := strings.Trim(re.ReplaceAllString(strings.ToLower(strings.TrimSpace(value)), "-"), "-")
	if slug == "" {
		return "project"
	}
	return slug
}

func titleFromProjectKey(projectKey, root string) string {
	base := filepath.Base(root)
	if strings.TrimSpace(base) == "" || base == "." || base == string(filepath.Separator) {
		base = projectKey
	}
	base = strings.ReplaceAll(base, "-", " ")
	base = strings.ReplaceAll(base, "_", " ")
	words := strings.Fields(base)
	for index, word := range words {
		if len(word) == 0 {
			continue
		}
		words[index] = strings.ToUpper(word[:1]) + strings.ToLower(word[1:])
	}
	return strings.Join(words, " ")
}

func resolvePath(path string) string {
	if strings.TrimSpace(path) == "" {
		path = "."
	}
	abs, err := filepath.Abs(path)
	if err != nil {
		return path
	}
	return abs
}

func appendIfMissing(items []string, value string) []string {
	for _, item := range items {
		if item == value {
			return items
		}
	}
	return append(items, value)
}

func appendUnique(items []string, value string) []string {
	for _, item := range items {
		if strings.EqualFold(item, value) {
			return items
		}
	}
	return append(items, value)
}

func uniqueStrings(items []string) []string {
	seen := map[string]bool{}
	var result []string
	for _, item := range items {
		trimmed := strings.TrimSpace(item)
		if trimmed == "" {
			continue
		}
		key := strings.ToLower(trimmed)
		if seen[key] {
			continue
		}
		seen[key] = true
		result = append(result, trimmed)
	}
	return result
}

func take[T any](items []T, count int) []T {
	if len(items) <= count {
		return items
	}
	return items[:count]
}

func contains(items []string, target string) bool {
	for _, item := range items {
		if item == target {
			return true
		}
	}
	return false
}

func containsAny(text string, patterns ...string) bool {
	for _, pattern := range patterns {
		if strings.Contains(text, pattern) {
			return true
		}
	}
	return false
}

func blankToNil(value string) any {
	if strings.TrimSpace(value) == "" {
		return nil
	}
	return value
}

func fileExists(path string) bool {
	info, err := os.Stat(path)
	return err == nil && !info.IsDir()
}

func getenv(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func fail(err error) {
	_, _ = fmt.Fprintln(os.Stderr, err)
	if runtime.GOOS == "windows" {
	}
	os.Exit(1)
}
