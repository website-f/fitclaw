param(
  [string]$Python = "python",
  [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"

$agentRoot = Resolve-Path (Join-Path $PSScriptRoot "..\\..")
$distDir = Join-Path $agentRoot "dist"
$buildDir = Join-Path $agentRoot "build-output"

New-Item -ItemType Directory -Force -Path $distDir | Out-Null
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null

Push-Location $agentRoot

& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt -r build-requirements.txt

& $Python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name PersonalAIOpsAgent `
  --distpath dist `
  --workpath build-output\\pyinstaller `
  --specpath build-output\\spec `
  agent_daemon.py

$iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
if ($iscc) {
  & $iscc.Source "/DAppVersion=$Version" "packaging\\windows\\AgentSetup.iss"
} else {
  Write-Warning "Inno Setup was not found. The standalone exe is ready at agent_daemon\\dist\\PersonalAIOpsAgent.exe."
}

Pop-Location

