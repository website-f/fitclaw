package main

import (
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"strings"
)

type designPayload struct {
	Name        string   `json:"name"`
	Title       string   `json:"title,omitempty"`
	Prompt      string   `json:"prompt"`
	Description string   `json:"description,omitempty"`
	Tags        []string `json:"tags"`
	ImagePaths  []string `json:"image_paths"`
	SourceURL   string   `json:"source_url,omitempty"`
	ProjectKey  string   `json:"project_key,omitempty"`
}

type designResponse struct {
	ID          int      `json:"id"`
	Name        string   `json:"name"`
	Title       string   `json:"title"`
	Prompt      string   `json:"prompt"`
	Description string   `json:"description"`
	Tags        []string `json:"tags"`
	ImagePaths  []string `json:"image_paths"`
	SourceURL   string   `json:"source_url"`
	ProjectKey  string   `json:"project_key"`
	CreatedAt   string   `json:"created_at"`
	UpdatedAt   string   `json:"updated_at"`
}

func runDesignCommand(cfg config, args []string) error {
	if len(args) == 0 {
		return errors.New("usage: memorycore design {save|list|show NAME|delete NAME}")
	}
	switch args[0] {
	case "save":
		return runDesignSave(cfg, args[1:])
	case "list":
		return runDesignList(cfg, args[1:])
	case "show":
		if len(args) < 2 {
			return errors.New("usage: memorycore design show NAME")
		}
		return runDesignShow(cfg, args[1])
	case "delete":
		if len(args) < 2 {
			return errors.New("usage: memorycore design delete NAME")
		}
		return runDesignDelete(cfg, args[1])
	default:
		return fmt.Errorf("unknown design subcommand: %s", args[0])
	}
}

func runDesignSave(cfg config, args []string) error {
	// Slices start nil. We initialize to empty so the JSON body sends
	// `"tags": []` instead of `"tags": null` — small, but Pydantic is
	// stricter about nulls than empty lists.
	payload := designPayload{
		Tags:       []string{},
		ImagePaths: []string{},
	}

	for index := 0; index < len(args); index++ {
		token := args[index]
		switch token {
		case "--name":
			index++
			if index >= len(args) {
				return errors.New("--name requires a value")
			}
			payload.Name = args[index]
		case "--title":
			index++
			if index >= len(args) {
				return errors.New("--title requires a value")
			}
			payload.Title = args[index]
		case "--prompt":
			index++
			if index >= len(args) {
				return errors.New("--prompt requires a value")
			}
			payload.Prompt = args[index]
		case "--description", "--desc":
			index++
			if index >= len(args) {
				return errors.New("--description requires a value")
			}
			payload.Description = args[index]
		case "--tag":
			index++
			if index >= len(args) {
				return errors.New("--tag requires a value")
			}
			payload.Tags = append(payload.Tags, args[index])
		case "--image":
			index++
			if index >= len(args) {
				return errors.New("--image requires a value")
			}
			payload.ImagePaths = append(payload.ImagePaths, args[index])
		case "--source-url":
			index++
			if index >= len(args) {
				return errors.New("--source-url requires a value")
			}
			payload.SourceURL = args[index]
		case "--project":
			index++
			if index >= len(args) {
				return errors.New("--project requires a value")
			}
			payload.ProjectKey = args[index]
		default:
			return fmt.Errorf("unknown flag: %s", token)
		}
	}

	if payload.Name == "" {
		return errors.New("--name is required")
	}
	if payload.Prompt == "" {
		return errors.New("--prompt is required")
	}

	var result designResponse
	path := "/api/v1/memorycore/designs/" + url.PathEscape(payload.Name)
	if err := requestJSON(http.MethodPut, cfg.ServerURL, path, map[string]string{"user_id": cfg.UserID}, payload, &result); err != nil {
		return err
	}
	fmt.Printf("Saved design `%s` (id=%d, %d tags, %d images)\n",
		result.Name, result.ID, len(result.Tags), len(result.ImagePaths))
	return nil
}

func runDesignList(cfg config, args []string) error {
	query := map[string]string{"user_id": cfg.UserID}
	for index := 0; index < len(args); index++ {
		token := args[index]
		switch token {
		case "--query", "--q":
			index++
			if index >= len(args) {
				return errors.New("--query requires a value")
			}
			query["q"] = args[index]
		case "--tag":
			index++
			if index >= len(args) {
				return errors.New("--tag requires a value")
			}
			query["tag"] = args[index]
		default:
			return fmt.Errorf("unknown flag: %s", token)
		}
	}

	var rows []designResponse
	if err := requestJSON(http.MethodGet, cfg.ServerURL, "/api/v1/memorycore/designs", query, nil, &rows); err != nil {
		return err
	}
	if len(rows) == 0 {
		fmt.Println("No designs match.")
		return nil
	}
	for _, row := range rows {
		title := row.Title
		if title == "" {
			title = "(no title)"
		}
		fmt.Printf("- %s  %s  [%s]\n", row.Name, title, strings.Join(row.Tags, ", "))
	}
	return nil
}

func runDesignShow(cfg config, name string) error {
	var row designResponse
	path := "/api/v1/memorycore/designs/" + url.PathEscape(name)
	if err := requestJSON(http.MethodGet, cfg.ServerURL, path, map[string]string{"user_id": cfg.UserID}, nil, &row); err != nil {
		return err
	}

	fmt.Printf("Name:    %s\n", row.Name)
	if row.Title != "" {
		fmt.Printf("Title:   %s\n", row.Title)
	}
	if len(row.Tags) > 0 {
		fmt.Printf("Tags:    %s\n", strings.Join(row.Tags, ", "))
	}
	if row.ProjectKey != "" {
		fmt.Printf("Project: %s\n", row.ProjectKey)
	}
	fmt.Printf("Updated: %s\n\nPrompt:\n%s\n", row.UpdatedAt, row.Prompt)
	if row.Description != "" {
		fmt.Printf("\nDescription:\n%s\n", row.Description)
	}
	if len(row.ImagePaths) > 0 {
		fmt.Println("\nImages:")
		for _, path := range row.ImagePaths {
			fmt.Printf("  - %s\n", path)
		}
	}
	if row.SourceURL != "" {
		fmt.Printf("\nSource: %s\n", row.SourceURL)
	}
	return nil
}

func runDesignDelete(cfg config, name string) error {
	var result map[string]any
	path := "/api/v1/memorycore/designs/" + url.PathEscape(name)
	if err := requestJSON(http.MethodDelete, cfg.ServerURL, path, map[string]string{"user_id": cfg.UserID}, nil, &result); err != nil {
		return err
	}
	if deleted, _ := result["deleted"].(bool); deleted {
		fmt.Printf("Deleted design `%s`.\n", name)
	} else {
		fmt.Printf("No design named `%s` was found.\n", name)
	}
	return nil
}
