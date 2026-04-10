# MemoryCore Guide

`MemoryCore` is the project-memory layer for this platform.

It is meant to solve a practical problem:

- new Codex or Claude Code sessions burn time re-learning the same repo
- new machines lose local context
- your preferences are scattered across prompts instead of stored once

## What MemoryCore does

MemoryCore gives you two layers of reusable memory:

1. **Global profile memory**
   Your standing preferences, coding style, workflow habits, and notes.
2. **Project memory**
   A reusable snapshot of a specific repo:
   - summary
   - stack
   - important files
   - common commands
   - project notes
   - structure snapshot

The server copy is the source of truth.
You can pull it onto any machine later as a local `MEMORYCORE.md`.

## What it does not do

It does **not** magically force external tools to read your remote database.

For external tools like Codex or Claude Code, the practical path is:

1. save project memory to the server
2. pull it back into the repo as `MEMORYCORE.md`
3. let the next coding session use that file as standing context

Inside this system itself, the saved **global profile** is also injected into the app chat context automatically.
Inside `/app`, the **Memory Core** panel can also:

- browse saved project memories
- delete one or many memories
- download a launcher bundle
- download the selected `MEMORYCORE.md`

## API endpoints

Base prefix:

```text
/api/v1/memorycore
```

Available routes:

- `GET /profile?user_id=...`
- `PUT /profile?user_id=...`
- `DELETE /profile?user_id=...`
- `GET /projects?user_id=...`
- `DELETE /projects?user_id=...`
- `GET /projects/{project_key}?user_id=...`
- `PUT /projects/{project_key}?user_id=...`
- `GET /projects/{project_key}/markdown?user_id=...`
- `DELETE /projects/{project_key}?user_id=...`
- `DELETE /?user_id=...`

## CLI commands

Use either:

```powershell
python .\memorycore.py ...
```

or on Windows:

```powershell
.\memorycore.ps1 ...
```

or from `cmd.exe`:

```bat
memorycore.cmd ...
```

or from bash / macOS terminal:

```bash
./memorycore ...
```

You can also point it at another repo path.

## Natural terminal trigger

You can trigger MemoryCore with a natural phrase instead of a structured subcommand.

Examples:

```powershell
python .\memorycore.py hey memorycore, please remember this whole thing
```

```powershell
.\memorycore.ps1 hey fitclaw, list my projects
```

```bash
./memorycore hey memorycore, forget this project
```

The natural trigger currently understands actions like:

- remember this whole thing
- list my projects
- show this project memory
- pull this project memory
- forget this project
- clear all memory
- remember this preference: ...

## Launcher bundle from `/app`

In the `/app` sidebar, open **Memory Core** and:

1. choose a wake name like `jarvis`
2. choose the target platform
3. click **Download installable bundle**
4. extract it on your PC or Mac
5. double-click the included install helper
6. reopen your terminal

Then you can use:

```text
jarvis remember this whole thing
```

or:

```text
hey jarvis remember this whole thing
```

That standalone bundle does not require local Python.
By default, `remember this whole thing` saves the project memory to the server and also writes a local `MEMORYCORE.md` in the current project folder.

## Native installers from GitHub Actions

If you want a proper installer artifact instead of the `/app` bundle, use the GitHub Actions workflow:

- `Build MemoryCore Installers`

It produces:

- Windows: versioned setup `.exe` plus a portable zip
- macOS: versioned `.pkg`, `.dmg`, and a portable zip

The workflow asks for:

- `server_url`
- `user_id`
- `wake_name`

Those values are baked into the generated launchers, so users can install and type:

```text
jarvis remember this whole thing
```

or:

```text
hey jarvis remember this whole thing
```

without manually passing `--server-url` or `--user-id`.

## Set your global profile

Example:

```powershell
python .\memorycore.py --server-url http://84.46.249.133:8000 --user-id fitclaw `
  profile set `
  --display-name "Fitri" `
  --preference "Prefer concise but high-signal answers" `
  --coding-preference "Prefer practical implementation over long theory" `
  --coding-preference "Preserve existing repo style when editing" `
  --workflow-preference "Give me the quickest working path first" `
  --note "I often switch between multiple PCs and want synced context"
```

Show the current profile:

```powershell
python .\memorycore.py --server-url http://84.46.249.133:8000 --user-id fitclaw profile show
```

## Save a project snapshot

From inside a repo:

```powershell
python C:\path\to\personal-ai-ops-platform\memorycore.py `
  --server-url http://84.46.249.133:8000 `
  --user-id fitclaw `
  project save `
  --path . `
  --goal "Ship the mobile agent build reliably" `
  --preference "Keep mobile setup flows simple" `
  --note "The Android wrapper must work with plain http VPS URLs too" `
  --write-local
```

What that does:

- scans the repo
- stores a remote project memory snapshot
- writes a local `MEMORYCORE.md`

## Pull a project memory onto another machine

Example:

```powershell
python C:\path\to\personal-ai-ops-platform\memorycore.py `
  --server-url http://84.46.249.133:8000 `
  --user-id fitclaw `
  project pull `
  --project-key personal-ai-ops-platform `
  --output C:\projects\personal-ai-ops-platform\MEMORYCORE.md
```

This is the part that makes the system useful across device changes.

## List saved projects

```powershell
python .\memorycore.py --server-url http://84.46.249.133:8000 --user-id fitclaw project list
```

## Show or delete a project memory

```powershell
python .\memorycore.py --server-url http://84.46.249.133:8000 --user-id fitclaw project show --project-key personal-ai-ops-platform
```

```powershell
python .\memorycore.py --server-url http://84.46.249.133:8000 --user-id fitclaw project delete --project-key personal-ai-ops-platform
```

```powershell
python .\memorycore.py --server-url http://84.46.249.133:8000 --user-id fitclaw project clear
```

## Suggested workflow

For each important project:

1. save the project memory after major structure changes
2. keep `MEMORYCORE.md` in the repo root
3. pull the latest memory when you move to a new machine
4. refresh the project memory after architecture or workflow changes

## Recommended practical usage with coding tools

For Codex or Claude Code:

1. pull `MEMORYCORE.md`
2. keep it near the repo root
3. start the session in the repo
4. ask the assistant to use `MEMORYCORE.md` as standing project context

That gives you a lightweight portable memory layer without needing the tool to natively support your remote database.
