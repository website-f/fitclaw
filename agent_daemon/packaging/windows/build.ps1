param(
  [string]$Python = "python",
  [string]$Version = ""
)

$ErrorActionPreference = "Stop"

$agentRoot = Resolve-Path (Join-Path $PSScriptRoot "..\\..")
$distDir = Join-Path $agentRoot "dist"
$buildDir = Join-Path $agentRoot "build-output"
$versionFile = Join-Path $agentRoot "VERSION"

if ([string]::IsNullOrWhiteSpace($Version)) {
  if (Test-Path $versionFile) {
    $Version = (Get-Content $versionFile -Raw).Trim()
  } else {
    $Version = "0.1.0"
  }
}

New-Item -ItemType Directory -Force -Path $distDir | Out-Null
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null

Get-ChildItem $distDir -Filter "PersonalAIOpsAgent*.exe" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue

Push-Location $agentRoot

& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt -r build-requirements.txt

& $Python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name PersonalAIOpsAgent `
  --hidden-import pyscreeze `
  --hidden-import pymsgbox `
  --hidden-import pyrect `
  --hidden-import mouseinfo `
  --hidden-import pygetwindow `
  --collect-data pyautogui `
  --collect-data pyscreeze `
  --collect-data mouseinfo `
  --collect-data PIL `
  --collect-data customtkinter `
  --distpath dist `
  --workpath build-output\\pyinstaller `
  --specpath build-output\\spec `
  agent_daemon.py

$iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
$setupPath = Join-Path $distDir "PersonalAIOpsAgentSetup.exe"
if ($iscc) {
  & $iscc.Source "/DAppVersion=$Version" "packaging\\windows\\AgentSetup.iss"
} else {
  Write-Warning "Inno Setup was not found. The standalone exe is ready at agent_daemon\\dist\\PersonalAIOpsAgent.exe."
}

$canonicalExe = Join-Path $distDir "PersonalAIOpsAgent.exe"
$versionedExe = Join-Path $distDir "PersonalAIOpsAgent-$Version-windows-x64.exe"
if (Test-Path $canonicalExe) {
  Rename-Item -Path $canonicalExe -NewName (Split-Path $versionedExe -Leaf) -Force
}

if (Test-Path $setupPath) {
  $versionedSetup = Join-Path $distDir "PersonalAIOpsAgent-$Version-windows-x64-setup.exe"
  Rename-Item -Path $setupPath -NewName (Split-Path $versionedSetup -Leaf) -Force
}

Pop-Location
