# Mobile Wrapper

This folder is a Capacitor wrapper around the hosted FitClaw AI Ops PWA.

## What it does

- loads the live web app from your server
- gives you a native Android and iOS project structure later
- keeps the web UI as the single source of truth

## Set the hosted URL

Before syncing Capacitor, point it at your deployed web app:

```bash
cd mobile_wrapper
export FITCLAW_PWA_URL=http://84.46.249.133:8000/app
```

On Windows PowerShell:

```powershell
$env:FITCLAW_PWA_URL="http://84.46.249.133:8000/app"
```

## Install dependencies

```bash
cd mobile_wrapper
npm install
```

## Add platforms

```bash
npm run cap:add:android
npm run cap:add:ios
```

## Sync and open native projects

```bash
npm run cap:sync
npm run cap:open:android
npm run cap:open:ios
```

## Notes

- For App Store and Play Store release, HTTPS plus a domain is strongly recommended.
- If you want the wrapper to bundle local web assets instead of loading the remote server URL, you can switch the Capacitor config later to a compiled local build.
