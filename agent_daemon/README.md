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

## GitHub Actions

The repository includes automated builds:

- `.github/workflows/build-agent-windows.yml`
- `.github/workflows/build-agent-macos.yml`

## Build Windows

```powershell
cd agent_daemon
powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
```

## Build macOS

```bash
cd agent_daemon
bash packaging/macos/build.sh
```

## Control panel

After the server is up, open:

```text
http://YOUR_VPS_IP:8000/control
```

That panel sends direct control commands to the installed agent.
