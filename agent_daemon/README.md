# Desktop Agent Installer

This folder contains the installable desktop agent foundation.

## Entry points

- `agent_daemon.py` opens the setup UI by default
- `python agent_daemon.py run-agent` runs the background daemon directly

## Capabilities

The installed agent can now:

- register and heartbeat to the VPS
- run queued background tasks
- capture screenshots for live view
- move, click, and drag the mouse
- type text, press keys, and send hotkeys
- browse files and read file contents
- list and kill processes
- list windows and focus a window
- launch apps
- run safe app-specific actions:
  - open a URL in the default browser
  - reveal a path in the file manager
  - open a path in VS Code

## Packaging targets

- Windows standalone app + Inno Setup installer
- macOS `.app` + `.pkg`
- Windows and macOS release artifacts now use versioned filenames from `agent_daemon/VERSION`

## GitHub Actions

The repository includes automated builds:

- `.github/workflows/build-agent-windows.yml`
- `.github/workflows/build-agent-macos.yml`
- `.github/workflows/build-mobile-agent-android.yml`
- `.github/workflows/build-mobile-agent-ios.yml`
- `.github/workflows/build-agent-all-platforms.yml`

All agent workflows now stage their outputs into `agent_daemon/dist` on the GitHub runner before uploading artifacts.

Important:

- GitHub Actions cannot directly place files into your local machine folder by itself
- after the workflow finishes, download the artifact and extract it
- the extracted artifact preserves the `agent_daemon/dist` layout

If you want one-click packaging for every agent platform in a single run, use:

- `.github/workflows/build-agent-all-platforms.yml`

That workflow bundles:

- Windows `.exe`
- Windows setup installer
- macOS `.app`
- macOS `.pkg`
- macOS `.dmg`
- Android `.apk`
- iOS simulator `.zip`

## Build Windows

```powershell
cd agent_daemon
powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
```

Example output:

```text
agent_daemon/dist/PersonalAIOpsAgent-0.3.6-windows-x64.exe
```

## Build macOS

```bash
cd agent_daemon
bash packaging/macos/build.sh
```

Example outputs:

```text
agent_daemon/dist/PersonalAIOpsAgent-0.3.6-macos.app
agent_daemon/dist/PersonalAIOpsAgent-0.3.6-macos.pkg
agent_daemon/dist/PersonalAIOpsAgent-0.3.6-macos.dmg
```

## Control panel

After the server is up, open:

```text
http://YOUR_VPS_IP:8000/control
```

That panel sends direct control commands to the installed agent.
