# Caddy Reverse Proxy Guide

Use this pattern when one VPS will host many projects and many domains.

## Recommended layout

Keep your app repos separate and run one shared edge proxy for the whole VPS:

```text
/opt/
|-- reverse-proxy/
|   |-- Caddyfile
|   `-- docker-compose.yml
|-- personal-ai-ops-platform/
|-- another-app/
`-- anything-else/
```

Recommended:

- one shared Caddy stack in `/opt/reverse-proxy`
- one repo per app in its own `/opt/<project>` folder
- each app publishes only its own local port
- only Caddy binds to public `80` and `443`

Avoid putting a separate Caddy container inside every app repo. That becomes painful once multiple projects all want the same `80/443` ports, certificate storage, redirects, and TLS settings.

## Why this works well

- Caddy owns HTTPS certificates in one place
- every new domain is just one more site block in one `Caddyfile`
- app repos stay portable and do not need to know about each other
- you can restart or redeploy one app without touching the VPS edge proxy

## Prepare this project for shared Caddy

In this repo, set the published ports to localhost only in `.env`:

```env
API_BIND_IP=127.0.0.1
N8N_BIND_IP=127.0.0.1
FLOWER_BIND_IP=127.0.0.1
OLLAMA_BIND_IP=127.0.0.1
```

Then restart the stack:

```bash
cd /opt/personal-ai-ops-platform
docker compose up -d
```

Notes:

- `API_BIND_IP=127.0.0.1` means the app is reachable from the VPS itself and from Caddy, but not directly from the public internet.
- `OLLAMA_BIND_IP=127.0.0.1` is the safer default. Only keep Ollama public if you have a very specific reason.
- `N8N_HOST` should be set to the final n8n domain if you expose n8n behind Caddy, for example `n8n.example.com`.
- The shared Caddy container uses host networking in this guide so it can proxy to `127.0.0.1` on the VPS.

## Shared Caddy stack

Create `/opt/reverse-proxy` on the VPS and copy these example files from this repo:

- `deploy/caddy/docker-compose.yml.example`
- `deploy/caddy/Caddyfile.example`

Rename them to:

- `/opt/reverse-proxy/docker-compose.yml`
- `/opt/reverse-proxy/Caddyfile`

Example shared stack:

```yaml
services:
  caddy:
    image: caddy:2
    container_name: shared-caddy
    restart: unless-stopped
    network_mode: host
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config

volumes:
  caddy_data:
  caddy_config:
```

Example `Caddyfile`:

```caddy
{
    email you@example.com
}

aiops.example.com {
    encode gzip zstd
    reverse_proxy 127.0.0.1:8000
}

n8n.example.com {
    encode gzip zstd
    reverse_proxy 127.0.0.1:5678
}
```

Bring it up:

```bash
cd /opt/reverse-proxy
docker compose up -d
```

## DNS setup

For each domain or subdomain, create an `A` record pointing to your VPS public IP.

Examples:

- `aiops.example.com -> 84.46.249.133`
- `n8n.example.com -> 84.46.249.133`

Caddy handles the TLS certificate automatically after DNS resolves.

## Firewall

For the shared-proxy setup, open:

- `80/tcp`
- `443/tcp`

You usually do not need to keep `8000`, `5678`, or `5555` open publicly once those services are bound to `127.0.0.1`.

## Good defaults for this project

- `aiops.example.com` -> proxy to the FastAPI app on port `8000`
- `n8n.example.com` -> proxy to `5678` only if you really need web access to n8n
- keep Flower private unless you have a strong reason to publish it
- keep Ollama private unless you are protecting it with a VPN or another access layer

## Practical answer for your VPS plan

Best long-term setup:

1. Put `personal-ai-ops-platform` in `/opt/personal-ai-ops-platform`.
2. Put one shared Caddy stack in `/opt/reverse-proxy`.
3. Point every future domain to the VPS IP.
4. Add a new Caddy site block for each project.
5. Bind each project to localhost-only ports unless it truly needs public direct access.
