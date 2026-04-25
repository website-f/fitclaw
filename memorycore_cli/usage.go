package main

import (
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"sort"
	"strconv"
)

// Payload sent to POST /api/v1/memorycore/usage.
// Struct tags (e.g. `json:"session_id,omitempty"`) tell encoding/json how to
// marshal this into JSON keys. `omitempty` skips the field when empty so the
// server sees a clean body.
type usageLogPayload struct {
	Tool         string `json:"tool"`
	Model        string `json:"model"`
	SessionID    string `json:"session_id,omitempty"`
	ProjectKey   string `json:"project_key,omitempty"`
	InputTokens  int    `json:"input_tokens"`
	OutputTokens int    `json:"output_tokens"`
	CacheRead    int    `json:"cache_read_tokens,omitempty"`
	CacheWrite   int    `json:"cache_write_tokens,omitempty"`
	Note         string `json:"note,omitempty"`
}

// Response for POST /usage and items in GET /usage/sessions/{id}.
// Pointer *float64 is how Go models "nullable float" — nil when the server
// returned JSON null (i.e. no pricing for that model).
type usageLogResponse struct {
	ID           int      `json:"id"`
	Tool         string   `json:"tool"`
	Model        string   `json:"model"`
	InputTokens  int      `json:"input_tokens"`
	OutputTokens int      `json:"output_tokens"`
	CostUSD      *float64 `json:"cost_usd"`
	CreatedAt    string   `json:"created_at"`
}

type usageBreakdown struct {
	InputTokens      int     `json:"input_tokens"`
	OutputTokens     int     `json:"output_tokens"`
	CacheReadTokens  int     `json:"cache_read_tokens"`
	CacheWriteTokens int     `json:"cache_write_tokens"`
	CostUSD          float64 `json:"cost_usd"`
	Calls            int     `json:"calls"`
}

type usageSummary struct {
	Period     string                    `json:"period"`
	RangeStart string                    `json:"range_start"`
	RangeEnd   string                    `json:"range_end"`
	Total      usageBreakdown            `json:"total"`
	ByTool     map[string]usageBreakdown `json:"by_tool"`
	ByModel    map[string]usageBreakdown `json:"by_model"`
}

func runUsageCommand(cfg config, args []string) error {
	if len(args) == 0 {
		return errors.New("usage: memorycore usage {log|today|week|month|session SESSION_ID}")
	}
	switch args[0] {
	case "log":
		return runUsageLog(cfg, args[1:])
	case "today", "week", "month":
		return runUsageSummary(cfg, args[0])
	case "session":
		if len(args) < 2 {
			return errors.New("usage: memorycore usage session SESSION_ID")
		}
		return runUsageSession(cfg, args[1])
	default:
		return fmt.Errorf("unknown usage subcommand: %s", args[0])
	}
}

func runUsageLog(cfg config, args []string) error {
	payload := usageLogPayload{Tool: "claude_code"}

	for index := 0; index < len(args); index++ {
		token := args[index]
		switch token {
		case "--tool":
			index++
			if index >= len(args) {
				return errors.New("--tool requires a value")
			}
			payload.Tool = args[index]
		case "--model":
			index++
			if index >= len(args) {
				return errors.New("--model requires a value")
			}
			payload.Model = args[index]
		case "--session":
			index++
			if index >= len(args) {
				return errors.New("--session requires a value")
			}
			payload.SessionID = args[index]
		case "--project":
			index++
			if index >= len(args) {
				return errors.New("--project requires a value")
			}
			payload.ProjectKey = args[index]
		case "--in":
			index++
			if index >= len(args) {
				return errors.New("--in requires a value")
			}
			n, err := strconv.Atoi(args[index])
			if err != nil {
				return fmt.Errorf("--in: %w", err)
			}
			payload.InputTokens = n
		case "--out":
			index++
			if index >= len(args) {
				return errors.New("--out requires a value")
			}
			n, err := strconv.Atoi(args[index])
			if err != nil {
				return fmt.Errorf("--out: %w", err)
			}
			payload.OutputTokens = n
		case "--cache-read":
			index++
			if index >= len(args) {
				return errors.New("--cache-read requires a value")
			}
			n, err := strconv.Atoi(args[index])
			if err != nil {
				return fmt.Errorf("--cache-read: %w", err)
			}
			payload.CacheRead = n
		case "--cache-write":
			index++
			if index >= len(args) {
				return errors.New("--cache-write requires a value")
			}
			n, err := strconv.Atoi(args[index])
			if err != nil {
				return fmt.Errorf("--cache-write: %w", err)
			}
			payload.CacheWrite = n
		case "--note":
			index++
			if index >= len(args) {
				return errors.New("--note requires a value")
			}
			payload.Note = args[index]
		default:
			return fmt.Errorf("unknown flag: %s", token)
		}
	}

	if payload.Model == "" {
		return errors.New("--model is required")
	}

	var result usageLogResponse
	query := map[string]string{"user_id": cfg.UserID}
	if err := requestJSON(http.MethodPost, cfg.ServerURL, "/api/v1/memorycore/usage", query, payload, &result); err != nil {
		return err
	}
	fmt.Printf("Logged usage id=%d  %s/%s  in=%d out=%d  cost=%s\n",
		result.ID, result.Tool, result.Model,
		result.InputTokens, result.OutputTokens, formatCost(result.CostUSD))
	return nil
}

func runUsageSummary(cfg config, period string) error {
	var summary usageSummary
	query := map[string]string{"user_id": cfg.UserID, "period": period}
	if err := requestJSON(http.MethodGet, cfg.ServerURL, "/api/v1/memorycore/usage/summary", query, nil, &summary); err != nil {
		return err
	}
	fmt.Printf("MemoryCore usage — %s (%s → %s)\n", summary.Period, summary.RangeStart, summary.RangeEnd)
	fmt.Printf("  Total: %d calls  in=%d  out=%d  cost=$%.4f\n",
		summary.Total.Calls, summary.Total.InputTokens, summary.Total.OutputTokens, summary.Total.CostUSD)
	if len(summary.ByTool) > 0 {
		fmt.Println("  By tool:")
		printBreakdownMap(summary.ByTool)
	}
	if len(summary.ByModel) > 0 {
		fmt.Println("  By model:")
		printBreakdownMap(summary.ByModel)
	}
	return nil
}

func runUsageSession(cfg config, sessionID string) error {
	var rows []usageLogResponse
	path := "/api/v1/memorycore/usage/sessions/" + url.PathEscape(sessionID)
	if err := requestJSON(http.MethodGet, cfg.ServerURL, path, map[string]string{"user_id": cfg.UserID}, nil, &rows); err != nil {
		return err
	}
	if len(rows) == 0 {
		fmt.Printf("No usage rows for session %s\n", sessionID)
		return nil
	}
	for _, row := range rows {
		fmt.Printf("  %s  %s/%s  in=%d  out=%d  cost=%s\n",
			row.CreatedAt, row.Tool, row.Model,
			row.InputTokens, row.OutputTokens, formatCost(row.CostUSD))
	}
	return nil
}

func printBreakdownMap(m map[string]usageBreakdown) {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		b := m[k]
		fmt.Printf("    %-28s  calls=%d  in=%d  out=%d  cost=$%.4f\n",
			k, b.Calls, b.InputTokens, b.OutputTokens, b.CostUSD)
	}
}

func formatCost(cost *float64) string {
	if cost == nil {
		return "(unknown)"
	}
	return fmt.Sprintf("$%.6f", *cost)
}
