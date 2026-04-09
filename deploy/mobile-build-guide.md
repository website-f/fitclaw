# Mobile Build Guide

This guide covers the two mobile packaging lanes in this repo:

1. `mobile_wrapper/`
   The mobile agent companion app.
2. `mobile_webapp_wrapper/`
   The full FitClaw AI Ops web app shell for Android and iOS.

## What each wrapper is for

### Mobile agent wrapper

Folder:

- [`mobile_wrapper/`](../mobile_wrapper/)

Use this when you want a phone app that behaves like an agent companion:

- stores the server URL and agent credentials on-device
- tests the connection to your API
- registers and removes a mobile agent
- sends heartbeats back to your platform

Current scope:

- this is a mobile agent companion base
- it is not yet a full hidden always-on background mobile daemon

### Mobile web app wrapper

Folder:

- [`mobile_webapp_wrapper/`](../mobile_webapp_wrapper/)

Use this when you want the full `/app` experience inside an Android or iOS shell:

- chat UI
- automation UI
- model switching
- PWA-like experience inside a native wrapper

Current scope:

- it loads your hosted web app URL
- the server remains the source of truth

## What is already prepared

Both wrappers already have:

- `package.json`
- Capacitor configuration
- Android platform folder
- iOS platform folder
- GitHub Actions workflows

I also verified these wrapper commands locally:

- `npm ci`
- `npm run cap:ensure:android`
- `npm run cap:ensure:ios`

## Prerequisites

### For Android local builds

You need:

- Node.js
- Java JDK
- Android Studio
- Android SDK

Useful checks:

```powershell
node -v
npm -v
java -version
```

### For iOS local builds

You need:

- a macOS machine
- Xcode
- CocoaPods

iOS device builds and App Store publishing also require Apple signing.

## Agent app build

### Folder

```text
mobile_wrapper/
```

### Install dependencies

```powershell
cd mobile_wrapper
npm ci
```

### Ensure native platforms

```powershell
npm run cap:ensure:android
npm run cap:ensure:ios
```

### Open Android project

```powershell
npm run cap:open:android
```

If you want a debug APK from the command line on Windows:

```powershell
cd android
.\gradlew.bat assembleDebug
```

Expected output:

```text
mobile_wrapper/android/app/build/outputs/apk/debug/app-debug.apk
```

### Open iOS project

Run this on macOS:

```bash
cd mobile_wrapper
npm ci
npm run cap:ensure:ios
npm run cap:open:ios
```

For a simulator build on macOS:

```bash
cd mobile_wrapper/ios/App
pod install
xcodebuild \
  -workspace App.xcworkspace \
  -scheme App \
  -configuration Debug \
  -sdk iphonesimulator \
  -destination 'generic/platform=iOS Simulator' \
  CODE_SIGNING_ALLOWED=NO \
  build
```

What you get:

- simulator `.app` for testing
- for a real iPhone install, you still need Apple signing

## Full web app shell build

### Folder

```text
mobile_webapp_wrapper/
```

### Set the hosted URL first

The web app wrapper points to your deployed `/app`.

On Windows PowerShell:

```powershell
$env:FITCLAW_PWA_URL="https://YOUR_DOMAIN/app"
```

On macOS/Linux:

```bash
export FITCLAW_PWA_URL="https://YOUR_DOMAIN/app"
```

Important:

- for iPhone and proper install behavior, use `https://`
- avoid plain remote `http://` for production mobile use

### Install dependencies

```powershell
cd mobile_webapp_wrapper
npm ci
```

### Ensure native platforms

```powershell
npm run cap:ensure:android
npm run cap:ensure:ios
```

### Open Android project

```powershell
npm run cap:open:android
```

To build a debug APK from the command line:

```powershell
cd android
.\gradlew.bat assembleDebug
```

Expected output:

```text
mobile_webapp_wrapper/android/app/build/outputs/apk/debug/app-debug.apk
```

### Open iOS project

Run this on macOS:

```bash
cd mobile_webapp_wrapper
npm ci
export FITCLAW_PWA_URL="https://YOUR_DOMAIN/app"
npm run cap:ensure:ios
npm run cap:open:ios
```

For a simulator build:

```bash
cd mobile_webapp_wrapper/ios/App
pod install
xcodebuild \
  -workspace App.xcworkspace \
  -scheme App \
  -configuration Debug \
  -sdk iphonesimulator \
  -destination 'generic/platform=iOS Simulator' \
  CODE_SIGNING_ALLOWED=NO \
  build
```

## GitHub Actions builds

These workflows are already in the repo.

### Agent mobile wrapper

- [`.github/workflows/build-mobile-agent-android.yml`](../.github/workflows/build-mobile-agent-android.yml)
- [`.github/workflows/build-mobile-agent-ios.yml`](../.github/workflows/build-mobile-agent-ios.yml)
- [`.github/workflows/build-agent-all-platforms.yml`](../.github/workflows/build-agent-all-platforms.yml)

Artifacts:

- `PersonalAIOpsAgent-dist-android`
- `PersonalAIOpsAgent-dist-ios`
- `PersonalAIOpsAgent-dist-bundle-<version>` from the all-platform workflow

### Full web app wrapper

- [`.github/workflows/build-mobile-android.yml`](../.github/workflows/build-mobile-android.yml)
- [`.github/workflows/build-mobile-ios.yml`](../.github/workflows/build-mobile-ios.yml)

Artifacts:

- `FitClaw-AI-Ops-webapp-android-apk`
- `FitClaw-AI-Ops-webapp-ios-simulator-app`

### How to use GitHub Actions later

1. Push the repo to GitHub.
2. Open the repository in GitHub.
3. Go to `Actions`.
4. Pick the workflow you want.
5. Click `Run workflow`.
6. Download the artifact from the finished run.

For the agent builds, every workflow now stages outputs into `agent_daemon/dist` before uploading.

This means:

- the artifact already matches your `agent_daemon/dist` structure
- after downloading and extracting, your files are already organized the same way

If you want one run that collects Windows, macOS, Android, and iOS agent outputs into a single downloadable bundle, run:

- `Build Agent All Platforms Dist Bundle`

## Fastest practical path

If your goal is just to get something installable quickly:

### For Android

1. Build the agent app from `mobile_wrapper`
2. Build the full app shell from `mobile_webapp_wrapper`
3. Install the debug APKs on your Android device

### For iPhone

1. Use the hosted `/app` PWA first
2. Add it to Home Screen
3. Later, use the iOS workflow or a Mac with Xcode for a native shell build

## Recommended production setup

Before wrapping the full web app:

- point a domain to your VPS
- put the site behind `https://`
- use the final production URL for `FITCLAW_PWA_URL`

Example:

```powershell
$env:FITCLAW_PWA_URL="https://aiops.yourdomain.com/app"
```

## Notes

- Android APK build is realistic on Windows once Java and Android SDK are installed.
- iOS device install requires macOS and Apple signing.
- The iOS GitHub Actions workflows currently build unsigned simulator apps, not App Store `.ipa` packages.
- The mobile agent wrapper and the full web app wrapper are separate on purpose, so you can ship them independently.
