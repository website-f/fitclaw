package main

import (
	"context"
	"math"
	"runtime"
	"time"

	"github.com/shirou/gopsutil/v4/cpu"
	"github.com/shirou/gopsutil/v4/disk"
	"github.com/shirou/gopsutil/v4/host"
	"github.com/shirou/gopsutil/v4/load"
	"github.com/shirou/gopsutil/v4/mem"
	"github.com/shirou/gopsutil/v4/process"
)

// collectStats gathers a snapshot of host metrics. Each subsystem call is
// isolated — if any single one errors (e.g. load average unavailable on
// Windows), we log-and-continue rather than failing the entire response.
// This matches the real-world semantic: "show me whatever you can get."
func collectStats(ctx context.Context, diskPath string) (statsResponse, error) {
	snap := statsResponse{
		CollectedAt: time.Now().UTC(),
		CPUCores:    runtime.NumCPU(),
	}

	// CPU percent needs a sampling window. 300ms is a reasonable trade:
	// short enough to feel responsive, long enough to be meaningful.
	if percents, err := cpu.PercentWithContext(ctx, 300*time.Millisecond, false); err == nil && len(percents) > 0 {
		snap.CPUPercent = roundTo(percents[0], 2)
	}

	if vm, err := mem.VirtualMemoryWithContext(ctx); err == nil {
		snap.MemUsedMB = vm.Used / (1024 * 1024)
		snap.MemTotalMB = vm.Total / (1024 * 1024)
		snap.MemPercent = roundTo(vm.UsedPercent, 2)
	}

	if d, err := disk.UsageWithContext(ctx, diskPath); err == nil {
		const gb = 1_000_000_000.0
		snap.DiskUsedGB = roundTo(float64(d.Used)/gb, 2)
		snap.DiskTotalGB = roundTo(float64(d.Total)/gb, 2)
		snap.DiskPercent = roundTo(d.UsedPercent, 2)
	}

	if uptime, err := host.UptimeWithContext(ctx); err == nil {
		snap.UptimeSec = uptime
	}

	if avg, err := load.AvgWithContext(ctx); err == nil {
		snap.LoadAvg1 = roundTo(avg.Load1, 2)
		snap.LoadAvg5 = roundTo(avg.Load5, 2)
		snap.LoadAvg15 = roundTo(avg.Load15, 2)
	}

	if info, err := host.InfoWithContext(ctx); err == nil {
		snap.Hostname = info.Hostname
	}

	if pids, err := process.PidsWithContext(ctx); err == nil {
		snap.Processes = len(pids)
	}

	return snap, nil
}

func roundTo(value float64, places int) float64 {
	shift := math.Pow(10, float64(places))
	return math.Round(value*shift) / shift
}
