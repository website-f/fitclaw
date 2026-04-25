# Multi-stage build — compile in a fat Go image, ship from a tiny Alpine.
# Final image is ~15 MB vs ~800 MB if we shipped the Go toolchain.

FROM golang:1.24-alpine AS builder

WORKDIR /src

# Copy go.mod first. If this doesn't change, Docker caches the
# `go mod download` layer — rebuilds only re-run when deps change.
COPY go.mod ./
RUN go mod download || true

# Now copy the source and build.
COPY . .
RUN go mod tidy && CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /out/vps_stats .

FROM alpine:3.20
RUN apk add --no-cache ca-certificates tzdata wget
COPY --from=builder /out/vps_stats /usr/local/bin/vps_stats
EXPOSE 8090
HEALTHCHECK --interval=20s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://localhost:8090/health || exit 1
ENTRYPOINT ["/usr/local/bin/vps_stats"]
