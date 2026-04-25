// vps_stats — tiny HTTP service exposing host system metrics.
//
// Endpoints:
//   GET /health  → "ok" (for docker healthcheck)
//   GET /stats   → JSON snapshot of CPU / RAM / disk / uptime
//
// Auth: if VPS_STATS_TOKEN is set, /stats requires `Authorization: Bearer <token>`.
// Set VPS_STATS_ADDR to change the listen address (default :8090).
//
// When running inside Docker, mount the host's /proc, /sys, /etc into
// /host/* and set HOST_PROC=/host/proc etc. gopsutil reads these env vars
// and reports the host's numbers instead of the container's.
package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"time"
)

var (
	serverAddr = getenv("VPS_STATS_ADDR", ":8090")
	apiToken   = os.Getenv("VPS_STATS_TOKEN")
	diskPath   = getenv("VPS_STATS_DISK_PATH", "/")
)

// statsResponse is the JSON shape returned by /stats.
// Every field has an explicit json tag so the server API is stable even
// if we rename Go fields later.
type statsResponse struct {
	CollectedAt time.Time `json:"collected_at"`
	Hostname    string    `json:"hostname"`
	CPUPercent  float64   `json:"cpu_percent"`
	CPUCores    int       `json:"cpu_cores"`
	MemUsedMB   uint64    `json:"mem_used_mb"`
	MemTotalMB  uint64    `json:"mem_total_mb"`
	MemPercent  float64   `json:"mem_percent"`
	DiskUsedGB  float64   `json:"disk_used_gb"`
	DiskTotalGB float64   `json:"disk_total_gb"`
	DiskPercent float64   `json:"disk_percent"`
	UptimeSec   uint64    `json:"uptime_sec"`
	LoadAvg1    float64   `json:"load_avg_1"`
	LoadAvg5    float64   `json:"load_avg_5"`
	LoadAvg15   float64   `json:"load_avg_15"`
	Processes   int       `json:"processes"`
}

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", withMetrics("/health", handleHealth))
	mux.HandleFunc("/stats", withMetrics("/stats", withAuth(handleStats)))
	mux.HandleFunc("/processes", withMetrics("/processes", withAuth(handleProcesses)))
	mux.HandleFunc("/disks", withMetrics("/disks", withAuth(handleDisks)))
	mux.HandleFunc("/vscode", withMetrics("/vscode", withAuth(handleVSCode)))
	mux.HandleFunc("/claude_sessions", withMetrics("/claude_sessions", withAuth(handleClaudeSessions)))
	// /metrics stays unauthenticated by convention — Prometheus scrapers
	// need it and lock it down at the network layer (private network only).
	mux.Handle("/metrics", metricsHandler())

	log.Printf("vps_stats listening on %s (disk path=%s, auth=%v)",
		serverAddr, diskPath, apiToken != "")
	server := &http.Server{
		Addr:              serverAddr,
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
	}
	if err := server.ListenAndServe(); err != nil {
		log.Fatalf("server exited: %v", err)
	}
}

func handleHealth(w http.ResponseWriter, _ *http.Request) {
	w.WriteHeader(http.StatusOK)
	_, _ = fmt.Fprint(w, "ok")
}

func handleStats(w http.ResponseWriter, r *http.Request) {
	s, err := collectStats(r.Context(), diskPath)
	if err != nil {
		log.Printf("collect stats failed: %v", err)
		http.Error(w, "failed to collect stats", http.StatusInternalServerError)
		return
	}
	updateHostGauges(s)
	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(s); err != nil {
		log.Printf("encode failed: %v", err)
	}
}

// withAuth wraps an HTTP handler with a Bearer-token check.
// When VPS_STATS_TOKEN is empty we allow everything — useful for local dev
// but the docker-compose config below requires a token in production.
func withAuth(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if apiToken == "" {
			next(w, r)
			return
		}
		got := r.Header.Get("Authorization")
		if got != "Bearer "+apiToken {
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		next(w, r)
	}
}

func getenv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
