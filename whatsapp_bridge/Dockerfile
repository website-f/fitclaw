FROM golang:1.26-bookworm AS build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential pkg-config libsqlite3-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

COPY go.mod go.sum ./
RUN go mod download

COPY main.go ./
RUN CGO_ENABLED=1 GOOS=linux GOARCH=amd64 go build -o /out/whatsapp-bridge .

FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libsqlite3-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=build /out/whatsapp-bridge /usr/local/bin/whatsapp-bridge

ENV WHATSAPP_BRIDGE_SERVER_ADDR=:8080

VOLUME ["/app/store"]
EXPOSE 8080

CMD ["whatsapp-bridge"]
