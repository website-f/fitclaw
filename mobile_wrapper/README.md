# Mobile Agent Wrapper

This folder is the Capacitor wrapper for the FitClaw mobile agent companion app.

Full build guide:

- [`../deploy/mobile-build-guide.md`](../deploy/mobile-build-guide.md)

## What it is for

- package a mobile agent companion into Android and iOS projects
- store the server URL, agent name, and shared key on-device
- test agent connectivity from the phone
- register, heartbeat, and remove a mobile agent from your server

## What it is not yet

- not a full hidden background mobile daemon yet
- not a silent always-on Android service or iOS background runner yet
- not the full chat app shell

The full chat and automation app wrapper lives in [`../mobile_webapp_wrapper/`](../mobile_webapp_wrapper/).

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

Or let the helper ensure and sync the platform in one step:

```bash
npm run cap:ensure:android
npm run cap:ensure:ios
```

## Open native projects

```bash
npm run cap:open:android
npm run cap:open:ios
```

## GitHub Actions

The repository includes separate workflows for this mobile agent shell:

- `.github/workflows/build-mobile-agent-android.yml`
- `.github/workflows/build-mobile-agent-ios.yml`

The Android workflow now uploads a versioned artifact and stages a versioned APK into `agent_daemon/dist`, for example:

- `PersonalAIOpsAgent-mobile-agent-android-0.3.13`
- `PersonalAIOpsAgent-0.3.13-mobile-agent-android.apk`

## Notes

- The app bundles a local setup UI and talks to your hosted API directly.
- You still need the same agent shared key as your server `.env`.
- `https://` is still the best server URL for phones. The Android wrapper now also permits plain `http://` for VPS setups that are not behind TLS yet.
- Native plugins for push, camera, file access, location, and deeper background work can be layered in later without changing the folder structure.
