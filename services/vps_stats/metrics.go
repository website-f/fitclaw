package main

import (
	"net/http"
	"strconv"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

// Prometheus instruments — declared at package scope so every handler can
// record into the same metrics. `MustRegister` panics at startup if two
// instruments collide; that's intentional, we want it loud.
var (
	reqCounter = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "vps_stats_requests_total",
		Help: "Total HTTP requests served by vps_stats, by path and status.",
	}, []string{"path", "status"})

	reqDuration = prometheus.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "vps_stats_request_duration_seconds",
		Help:    "Request duration seconds by path.",
		Buckets: prometheus.DefBuckets,
	}, []string{"path"})

	hostCPU = prometheus.NewGauge(prometheus.GaugeOpts{
		Name: "vps_stats_host_cpu_percent",
		Help: "Last observed host CPU percent.",
	})

	hostMem = prometheus.NewGauge(prometheus.GaugeOpts{
		Name: "vps_stats_host_mem_percent",
		Help: "Last observed host memory percent.",
	})

	hostDisk = prometheus.NewGauge(prometheus.GaugeOpts{
		Name: "vps_stats_host_disk_percent",
		Help: "Last observed host disk percent (primary mount).",
	})
)

func init() {
	prometheus.MustRegister(reqCounter, reqDuration, hostCPU, hostMem, hostDisk)
}

// metricsHandler serves the Prometheus scrape endpoint.
// Uses the default Go+process collectors + our custom ones above.
func metricsHandler() http.Handler {
	return promhttp.Handler()
}

// withMetrics wraps a handler so every request records its status + duration.
// The statusRecorder is a 5-line trick to observe the status code written by
// an inner handler without replacing the http.ResponseWriter wholesale.
func withMetrics(path string, next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		sr := &statusRecorder{ResponseWriter: w, status: 200}
		next(sr, r)
		reqCounter.WithLabelValues(path, strconv.Itoa(sr.status)).Inc()
		reqDuration.WithLabelValues(path).Observe(time.Since(start).Seconds())
	}
}

type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (s *statusRecorder) WriteHeader(code int) {
	s.status = code
	s.ResponseWriter.WriteHeader(code)
}

// updateHostGauges is called after each /stats collection to refresh the
// Prometheus gauges. A ticker-based goroutine would also work but would
// duplicate the expensive gopsutil calls; reusing the /stats data path is
// simpler and cheaper.
func updateHostGauges(s statsResponse) {
	hostCPU.Set(s.CPUPercent)
	hostMem.Set(s.MemPercent)
	hostDisk.Set(s.DiskPercent)
}
