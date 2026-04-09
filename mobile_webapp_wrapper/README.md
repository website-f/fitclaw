# Mobile Web App Wrapper

This folder is a Capacitor wrapper around the hosted FitClaw AI Ops PWA.

Full build guide:

- [`../deploy/mobile-build-guide.md`](../deploy/mobile-build-guide.md)

## What it does

- loads the live web app from your server
- gives you a native Android and iOS project structure later
- keeps the web UI as the single source of truth

## Set the hosted URL

Before syncing Capacitor, point it at your deployed web app:

```bash
cd mobile_webapp_wrapper
export FITCLAW_PWA_URL=http://84.46.249.133:8000/app
```

On Windows PowerShell:

```powershell
$env:FITCLAW_PWA_URL="http://84.46.249.133:8000/app"
```

## Install dependencies

```bash
cd mobile_webapp_wrapper
npm install
```

## Add platforms

```bash
npm run cap:add:android
npm run cap:add:ios
```

Or let the helper ensure and sync the platform in one step:

```bash
npm run cap:ensure:android
npm run cap:ensure:ios
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
- The repository now includes GitHub Actions for:
  - Android debug APK: `.github/workflows/build-mobile-android.yml`
  - iOS unsigned simulator app: `.github/workflows/build-mobile-ios.yml`
- The iOS workflow builds a simulator `.app` without signing. For a real App Store `.ipa`, add Apple signing secrets later and extend that workflow.
- The separate mobile agent shell lives in [`../mobile_wrapper/`](../mobile_wrapper/).
