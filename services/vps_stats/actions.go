package main

import (
	"context"
	"encoding/json"
	"log"
	"math"
	"net/http"
	"sort"
	"strconv"
	"time"

	"github.com/shirou/gopsutil/v4/disk"
	"github.com/shirou/gopsutil/v4/process"
)

// processEntry is what /processes returns per row.
type processEntry struct {
	PID        int32   `json:"pid"`
	Name       string  `json:"name"`
	Username   string  `json:"username,omitempty"`
	CPUPercent float64 `json:"cpu_percent"`
	MemPercent float64 `json:"mem_percent"`
	MemRSSMB   uint64  `json:"mem_rss_mb"`
	CreateTime int64   `json:"create_time_ms,omitempty"`
}

// diskEntry is what /disks returns per mounted filesystem.
type diskEntry struct {
	Mountpoint  string  `json:"mountpoint"`
	Device      string  `json:"device"`
	Fstype      string  `json:"fstype"`
	TotalGB     float64 `json:"total_gb"`
	UsedGB      float64 `json:"used_gb"`
	FreeGB      float64 `json:"free_gb"`
	UsedPercent float64 `json:"used_percent"`
}

func handleProcesses(w http.ResponseWriter, r *http.Request) {
	top := 10
	if v := r.URL.Query().Get("top"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			top = n
			if top > 200 {
				top = 200 // hard cap — don't let callers enumerate everything
			}
		}
	}
	sortBy := r.URL.Query().Get("by")
	if sortBy != "mem" {
		sortBy = "cpu" // default
	}

	rows, err := collectProcesses(r.Context(), sortBy, top)
	if err != nil {
		log.Printf("processes collect failed: %v", err)
		http.Error(w, "failed to collect processes", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(rows)
}

func collectProcesses(ctx context.Context, sortBy string, top int) ([]processEntry, error) {
	procs, err := process.ProcessesWithContext(ctx)
	if err != nil {
		return nil, err
	}
	entries := make([]processEntry, 0, len(procs))
	for _, p := range procs {
		entry := processEntry{PID: p.Pid}
		// Non-fatal per-field: processes die mid-enumeration; skip broken fields.
		if name, err := p.NameWithContext(ctx); err == nil {
			entry.Name = name
		}
		if user, err := p.UsernameWithContext(ctx); err == nil {
			entry.Username = user
		}
		if cpu, err := p.CPUPercentWithContext(ctx); err == nil {
			entry.CPUPercent = roundTo(cpu, 2)
		}
		if memP, err := p.MemoryPercentWithContext(ctx); err == nil {
			entry.MemPercent = math.Round(float64(memP)*100) / 100
		}
		if memInfo, err := p.MemoryInfoWithContext(ctx); err == nil && memInfo != nil {
			entry.MemRSSMB = memInfo.RSS / (1024 * 1024)
		}
		if ct, err := p.CreateTimeWithContext(ctx); err == nil {
			entry.CreateTime = ct
		}
		entries = append(entries, entry)
	}

	sort.Slice(entries, func(i, j int) bool {
		if sortBy == "mem" {
			return entries[i].MemPercent > entries[j].MemPercent
		}
		return entries[i].CPUPercent > entries[j].CPUPercent
	})

	if len(entries) > top {
		entries = entries[:top]
	}
	return entries, nil
}

func handleDisks(w http.ResponseWriter, r *http.Request) {
	rows, err := collectDisks(r.Context())
	if err != nil {
		log.Printf("disks collect failed: %v", err)
		http.Error(w, "failed to collect disks", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(rows)
}

func collectDisks(ctx context.Context) ([]diskEntry, error) {
	// `all=false` skips virtual filesystems (tmpfs, overlay, etc).
	parts, err := disk.PartitionsWithContext(ctx, false)
	if err != nil {
		return nil, err
	}
	out := make([]diskEntry, 0, len(parts))
	const gb = 1_000_000_000.0
	for _, part := range parts {
		usage, err := disk.UsageWithContext(ctx, part.Mountpoint)
		if err != nil {
			continue
		}
		out = append(out, diskEntry{
			Mountpoint:  part.Mountpoint,
			Device:      part.Device,
			Fstype:      part.Fstype,
			TotalGB:     roundTo(float64(usage.Total)/gb, 2),
			UsedGB:      roundTo(float64(usage.Used)/gb, 2),
			FreeGB:      roundTo(float64(usage.Free)/gb, 2),
			UsedPercent: roundTo(usage.UsedPercent, 2),
		})
	}
	sort.Slice(out, func(i, j int) bool {
		return out[i].UsedPercent > out[j].UsedPercent
	})
	return out, nil
}

// Suppress "imported and not used" if the file is rebuilt without the
// `go` directive pulling time in via another path. Keeping it harmless.
var _ = time.Now
