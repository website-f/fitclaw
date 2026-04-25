package main

import "time"

func unixMillisNow() int64 {
	return time.Now().UnixMilli()
}

func formatUnixMS(ms int64) string {
	return time.UnixMilli(ms).UTC().Format(time.RFC3339)
}
