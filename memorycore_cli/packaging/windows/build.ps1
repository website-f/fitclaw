param(
  [string]$Version = "",
  [string]$ServerUrl = "http://localhost:8000",
  [string]$UserId = "fitclaw",
  [string]$WakeName = "jarvis"
)

$ErrorActionPreference = "Stop"

$memoryCoreRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$repoRoot = Resolve-Path (Join-Path $memoryCoreRoot "..")
$distDir = Join-Path $memoryCoreRoot "dist"
$buildDir = Join-Path $memoryCoreRoot "build-output"
$appMain = Join-Path $repoRoot "app\main.py"

function Normalize-WakeName {
  param([string]$Value)
  if ($null -eq $Value) {
    $Value = ""
  }
  $normalized = [regex]::Replace($Value.ToLowerInvariant().Trim(), "[^a-z0-9]+", "-").Trim("-")
  if ([string]::IsNullOrWhiteSpace($normalized)) {
    return "jarvis"
  }
  return $normalized
}

if ([string]::IsNullOrWhiteSpace($Version)) {
  $match = Select-String -Path $appMain -Pattern 'version="([^"]+)"' | Select-Object -First 1
  if (-not $match) {
    throw "Could not read the app version from $appMain"
  }
  $Version = $match.Matches[0].Groups[1].Value
}

$WakeName = Normalize-WakeName $WakeName

New-Item -ItemType Directory -Force -Path $distDir | Out-Null
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null

Get-ChildItem $distDir -Filter "MemoryCore*" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
foreach ($name in @("memorycore-bin.exe", "memorycore.cmd", "hey.cmd", "$WakeName.cmd", "Install MemoryCore.cmd", "README.txt")) {
  $path = Join-Path $distDir $name
  if (Test-Path $path) {
    Remove-Item -Force $path
  }
}

Push-Location $memoryCoreRoot

$env:CGO_ENABLED = "0"
$env:GOOS = "windows"
$env:GOARCH = "amd64"

go build -trimpath -ldflags "-s -w" -o (Join-Path $distDir "memorycore-bin.exe") .

$binaryName = "memorycore-bin.exe"
$escapedServer = $ServerUrl.Replace('"', '""')
$escapedUser = $UserId.Replace('"', '""')
$escapedWake = $WakeName.Replace('"', '""')

$memoryCoreWrapper = @"
@echo off
setlocal
set SCRIPT_DIR=%~dp0
set SERVER_URL=$escapedServer
set MEMORYCORE_USER=$escapedUser
"%SCRIPT_DIR%$binaryName" --server-url "%SERVER_URL%" --user-id "%MEMORYCORE_USER%" %*
"@

$heyWrapper = @"
@echo off
setlocal
if "%~1"=="" (
  echo Usage: hey $escapedWake remember this whole thing
  exit /b 1
)
if /I not "%~1"=="$escapedWake" (
  echo Wake name mismatch. Expected $escapedWake.
  exit /b 1
)
shift
set SCRIPT_DIR=%~dp0
set SERVER_URL=$escapedServer
set MEMORYCORE_USER=$escapedUser
"%SCRIPT_DIR%$binaryName" --server-url "%SERVER_URL%" --user-id "%MEMORYCORE_USER%" %*
"@

$wakeWrapper = @"
@echo off
setlocal
if "%~1"=="" (
  echo Usage: $escapedWake remember this whole thing
  exit /b 1
)
set SCRIPT_DIR=%~dp0
set SERVER_URL=$escapedServer
set MEMORYCORE_USER=$escapedUser
"%SCRIPT_DIR%$binaryName" --server-url "%SERVER_URL%" --user-id "%MEMORYCORE_USER%" %*
"@

$installHelper = @"
@echo off
setlocal
set SCRIPT_DIR=%~dp0
set TARGET_DIR=%LOCALAPPDATA%\Programs\MemoryCore
if not exist "%TARGET_DIR%" mkdir "%TARGET_DIR%"
copy /Y "%SCRIPT_DIR%$binaryName" "%TARGET_DIR%\$binaryName" >nul
copy /Y "%SCRIPT_DIR%memorycore.cmd" "%TARGET_DIR%\memorycore.cmd" >nul
copy /Y "%SCRIPT_DIR%hey.cmd" "%TARGET_DIR%\hey.cmd" >nul
copy /Y "%SCRIPT_DIR%$escapedWake.cmd" "%TARGET_DIR%\$escapedWake.cmd" >nul
copy /Y "%SCRIPT_DIR%README.txt" "%TARGET_DIR%\README.txt" >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "$target = Join-Path `$env:LOCALAPPDATA 'Programs\MemoryCore'; `$current = [Environment]::GetEnvironmentVariable('Path', 'User'); if ([string]::IsNullOrWhiteSpace(`$current)) { `$parts = @() } else { `$parts = `$current -split ';' | Where-Object { `$_ } }; `$normalizedTarget = `$target.TrimEnd('\'); `$exists = `$false; foreach (`$part in `$parts) { if (`$part.Trim().TrimEnd('\') -ieq `$normalizedTarget) { `$exists = `$true; break } }; if (-not `$exists) { `$newValue = @(`$parts + `$target) -join ';'; [Environment]::SetEnvironmentVariable('Path', `$newValue, 'User') }"
echo.
echo MemoryCore was installed to %TARGET_DIR%.
echo Reopen PowerShell or Command Prompt, then run:
echo   $escapedWake remember this whole thing
echo or
echo   hey $escapedWake remember this whole thing
pause
"@

$readme = @"
MemoryCore Portable Bundle
==========================

Server URL: $ServerUrl
User ID: $UserId
Wake name: $WakeName

Quick install:
1. Extract this zip anywhere.
2. Double-click Install MemoryCore.cmd
3. Reopen PowerShell or Command Prompt.
4. Run:
   $WakeName remember this whole thing
   or
   hey $WakeName remember this whole thing

Behavior:
- The command saves project memory to your MemoryCore server.
- It also writes a local MEMORYCORE.md in the current project folder by default.
- If you only want cloud save later, the hidden engine supports --no-write-local.
"@

Set-Content -Path (Join-Path $distDir "memorycore.cmd") -Value $memoryCoreWrapper -Encoding Ascii
Set-Content -Path (Join-Path $distDir "hey.cmd") -Value $heyWrapper -Encoding Ascii
Set-Content -Path (Join-Path $distDir "$WakeName.cmd") -Value $wakeWrapper -Encoding Ascii
Set-Content -Path (Join-Path $distDir "Install MemoryCore.cmd") -Value $installHelper -Encoding Ascii
Set-Content -Path (Join-Path $distDir "README.txt") -Value $readme -Encoding Ascii

$portableZip = Join-Path $distDir "MemoryCore-$Version-windows-x64-portable.zip"
$portableItems = @(
  (Join-Path $distDir $binaryName),
  (Join-Path $distDir "memorycore.cmd"),
  (Join-Path $distDir "hey.cmd"),
  (Join-Path $distDir "$WakeName.cmd"),
  (Join-Path $distDir "Install MemoryCore.cmd"),
  (Join-Path $distDir "README.txt")
)
Compress-Archive -Path $portableItems -DestinationPath $portableZip -Force

$iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
$setupPath = Join-Path $distDir "MemoryCoreSetup.exe"
if ($iscc) {
  & $iscc.Source "/DAppVersion=$Version" "packaging\windows\MemoryCoreSetup.iss"
} else {
  Write-Warning "Inno Setup was not found. Portable bundle is ready at $portableZip."
}

if (Test-Path $setupPath) {
  $versionedSetup = Join-Path $distDir "MemoryCore-$Version-windows-x64-setup.exe"
  Rename-Item -Path $setupPath -NewName (Split-Path $versionedSetup -Leaf) -Force
}

Pop-Location
