# VPS Deployment Guide

This guide assumes:

- your VPS is Ubuntu
- Docker and the Docker Compose plugin are already installed
- your repository will be pushed to GitHub
- your current VPS public IP is available

## 1. Connect to the VPS

```bash
ssh root@YOUR_VPS_IP
```

If you use a non-root sudo user, replace `root` with that username in the commands below.

## 2. Install Git

```bash
apt update
apt install -y git
```

## 3. Clone the repository

### Public repository

```bash
cd /opt
git clone https://github.com/YOUR_GITHUB_USERNAME/personal-ai-ops-platform.git
cd /opt/personal-ai-ops-platform
```

### Private repository with SSH

Generate an SSH key on the VPS:

```bash
ssh-keygen -t ed25519 -C "vps-deploy"
cat ~/.ssh/id_ed25519.pub
```

Add that public key to your GitHub account or repository deploy keys, then clone:

```bash
cd /opt
git clone git@github.com:YOUR_GITHUB_USERNAME/personal-ai-ops-platform.git
cd /opt/personal-ai-ops-platform
```

## 4. Create the environment file

```bash
cp .env.example .env
nano .env
```

Minimum values to set:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOWED_USER_IDS`
- `AGENT_API_SHARED_KEY`
- `N8N_BASIC_AUTH_PASSWORD`
- `N8N_HOST`
- `OLLAMA_MODEL`
- `OLLAMA_MODELS`

Recommended VPS values:

```env
APP_ENV=production
API_PORT=8000
TIMEZONE=Asia/Kuala_Lumpur

TELEGRAM_BOT_TOKEN=your-telegram-bot-token
TELEGRAM_ALLOWED_USER_IDS=your-telegram-user-id
DEFAULT_REPORT_CHAT_ID=

OLLAMA_MODEL=qwen2.5:3b
OLLAMA_MODELS=qwen2.5:3b,qwen2.5-coder:7b,gemma2:2b

GEMINI_API_KEY=
GEMINI_MODEL=gemini-1.5-flash

AGENT_BASIC_AUTH_USERNAME=agent
AGENT_API_SHARED_KEY=replace-with-a-long-random-secret

FLOWER_PORT=5555
OLLAMA_PORT=11434
N8N_PORT=5678
N8N_HOST=YOUR_VPS_IP_OR_DOMAIN
N8N_BASIC_AUTH_ACTIVE=true
N8N_BASIC_AUTH_USER=admin
N8N_BASIC_AUTH_PASSWORD=replace-with-a-strong-password
N8N_ENCRYPTION_KEY=replace-with-a-long-random-string
```

## 5. Start the stack

```bash
docker compose up -d --build
```

The first startup can take several minutes because Ollama pulls the models listed in `OLLAMA_MODELS`.

## 6. Check status

```bash
docker compose ps
docker compose logs -f api
```

Useful logs:

```bash
docker compose logs -f bot
docker compose logs -f ollama
docker compose logs -f worker
```

## 7. Open the firewall

If you use UFW:

```bash
ufw allow 22/tcp
ufw allow 8000/tcp
ufw allow 5678/tcp
ufw allow 5555/tcp
ufw allow 11434/tcp
ufw enable
ufw status
```

Recommended:

- keep `8000` open for the API and control panel
- open `11434` only if external tools like Continue need direct Ollama access
- open `5555` only if you want Flower available from outside
- open `5678` only if you want n8n available from outside

Redis is intentionally not published to the internet in the default Compose file.

## 8. Verify the running services

From your local machine:

- `http://YOUR_VPS_IP:8000/docs`
- `http://YOUR_VPS_IP:8000/health`
- `http://YOUR_VPS_IP:8000/app`
- `http://YOUR_VPS_IP:8000/control`
- `http://YOUR_VPS_IP:5678`
- `http://YOUR_VPS_IP:5555`

Expected result:

- `/health` returns healthy JSON
- `/app` opens the installable web chat app
- `/docs` opens Swagger UI
- `/control` loads the device control panel
- Telegram bot starts replying once `bot` is healthy

## 9. Connect your desktop agent

On your Windows or macOS machine, open the agent installer and use:

- Server URL: `http://YOUR_VPS_IP:8000`
- Username: `agent`
- Shared Key: the same value as `AGENT_API_SHARED_KEY`
- Agent Name: for example `office-pc`

Then click install/start. The agent should appear in:

- `http://YOUR_VPS_IP:8000/control`
- `GET /api/v1/control/agents`

## 10. Update after new GitHub commits

```bash
cd /opt/personal-ai-ops-platform
git pull
docker compose up -d --build
```

## 11. Auto-start on server reboot

Copy the included systemd unit:

```bash
cp deploy/systemd/personal-ai-ops-platform.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable personal-ai-ops-platform
systemctl start personal-ai-ops-platform
systemctl status personal-ai-ops-platform
```

If you keep the repo somewhere other than `/opt/personal-ai-ops-platform`, edit the `WorkingDirectory` in the service file first.

## 12. Common issues

### `http://YOUR_VPS_IP` shows nothing

That is expected unless something is bound to port 80. This project uses:

- `8000` for FastAPI
- `5678` for n8n
- `5555` for Flower
- `11434` for Ollama

So use the correct port in the browser.

### Telegram bot does not reply

Check:

```bash
docker compose logs -f bot
```

Usually the cause is one of:

- wrong `TELEGRAM_BOT_TOKEN`
- your Telegram user id is missing from `TELEGRAM_ALLOWED_USER_IDS`
- the stack was not rebuilt after editing `.env`

### Ollama is slow on first boot

That is normal during the first model pull. Check:

```bash
docker compose logs -f ollama
```

### Agent says offline

Check:

```bash
docker compose logs -f api
curl http://YOUR_VPS_IP:8000/api/v1/control/agents
```

Then confirm the desktop agent is using the right:

- server URL
- username
- shared key

## 13. Recommended next step

After the stack is working by IP, the next upgrade is:

- add a domain
- put Caddy or Nginx in front
- enable HTTPS

That is optional for now because the Telegram bot uses long polling and does not require a webhook.
