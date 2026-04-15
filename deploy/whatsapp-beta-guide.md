# WhatsApp Blasting Beta Guide

This beta now ships with an internal WhatsApp bridge inside `personal-ai-ops-platform`, so you do not need a sibling repo on the VPS.

Important:
- Do not use your main personal WhatsApp number.
- Keep this owner-only or opt-in only.
- Start with one allowlisted sender and one allowlisted recipient.
- Treat this as a beta convenience channel, not a bulk messaging platform.

## 1. Configure the platform

Add these to `.env`:

```env
WHATSAPP_BETA_ENABLED=true
WHATSAPP_BETA_ALLOW_INBOUND=true
WHATSAPP_BETA_ALLOW_BLASTING=false
WHATSAPP_BETA_BRIDGE_BASE_URL=http://whatsapp-bridge:8080/api
WHATSAPP_BETA_BRIDGE_API_TOKEN=replace-with-a-random-secret
WHATSAPP_BETA_SENDER_PHONE=60123456789
WHATSAPP_BETA_SENDER_LABEL=WhatsApp beta sender
WHATSAPP_BETA_DEFAULT_RECIPIENT=60123456789
WHATSAPP_BETA_ALLOWED_SENDERS=60123456789
WHATSAPP_BETA_ALLOWED_RECIPIENTS=60123456789
WHATSAPP_BETA_POLL_SECONDS=20
WHATSAPP_BETA_JITTER_MIN_SECONDS=20
WHATSAPP_BETA_JITTER_MAX_SECONDS=75
WHATSAPP_BETA_RECIPIENT_COOLDOWN_SECONDS=180
WHATSAPP_BETA_REPLY_MIN_SECONDS=3
WHATSAPP_BETA_REPLY_MAX_SECONDS=8
WHATSAPP_BETA_MAX_BLAST_RECIPIENTS=5
WHATSAPP_BETA_DAILY_LIMIT_PER_RECIPIENT=30
```

The bundled bridge exposes:
- `GET /api/health`
- `GET /api/recent-messages`
- `POST /api/send`
- `POST /api/download`

All endpoints accept `X-API-Key` when `WHATSAPP_BRIDGE_API_TOKEN` is set.

Low-risk first run:
- `WHATSAPP_BETA_ALLOW_BLASTING=false`
- one sender only
- one recipient only

## 2. Rebuild the stack

```bash
docker compose up -d --build api worker beat whatsapp-bridge
```

## 3. Pair the WhatsApp account

After the bridge starts for the first time, check the `whatsapp-bridge` container logs and scan the QR code with the WhatsApp account you want to use.

```bash
docker compose logs -f whatsapp-bridge
```

Use a secondary number, not your main personal number.

## 4. Open the beta page

Open:

```text
/whatsapp-beta
```

Use it to:
- verify bridge health
- save the sender phone and recipient allowlists inside the app
- send a single allowlisted test message
- queue a capped beta blast
- inspect recent WhatsApp beta events

## 5. Inbound AI chat

When inbound relay is enabled, allowlisted direct messages to the linked WhatsApp account can:
- chat with the AI
- ask for reports
- trigger the same safe agent/task flows already available in Telegram and `/app`

Examples:

```text
list agents
check storage on DESKTOP-0112K9I
weather in Kuala Lumpur now
ask DESKTOP-0112K9I to crawl https://example.com and summarize it
```

Safety notes:
- group chats are ignored
- non-allowlisted senders are ignored
- replies are slightly delayed to reduce robotic send patterns

## 6. What lowers risk

The platform wrapper adds:
- sender allowlists
- recipient allowlists
- outbound jitter
- per-recipient cooldowns
- daily caps
- duplicate suppression for repeated alerts
- event logging
- owner-visible warnings in the UI

This lowers risk. It does not remove risk.
