from __future__ import annotations

import json
import re
import time

from sqlalchemy.orm import Session

from app.models.agent import Agent, AgentStatus
from app.models.device_command import DeviceCommandStatus
from app.models.task import TaskStatus
from app.services.agent_service import AgentService
from app.services.device_control_service import DeviceControlService
from app.services.task_service import TaskService


class ControlWorkflowService:
    @staticmethod
    def get_agent_or_raise(db: Session, agent_name: str) -> Agent:
        AgentService.mark_stale_agents(db)
        agent = AgentService.get_agent(db, agent_name.strip())
        if agent is None:
            raise ValueError(f"Agent `{agent_name}` was not found.")
        return agent

    @staticmethod
    def inspect_storage(
        db: Session,
        agent_name: str,
        user_id: str | None = None,
        path: str | None = None,
        top_n: int = 10,
    ) -> dict:
        agent = ControlWorkflowService.get_agent_or_raise(db, agent_name)
        if agent.status != AgentStatus.online:
            raise ValueError(f"`{agent.name}` is currently `{agent.status.value}`.")

        prefers_direct = ControlWorkflowService._agent_supports_capability(agent, "storage")
        if prefers_direct:
            try:
                return ControlWorkflowService._run_storage_direct(db, agent, user_id, path, top_n)
            except ValueError as exc:
                if not ControlWorkflowService._should_use_storage_fallback(str(exc)):
                    raise

        return ControlWorkflowService._run_storage_fallback(db, agent, user_id, path, top_n)

    @staticmethod
    def delete_path(
        db: Session,
        agent_name: str,
        path: str,
        user_id: str | None = None,
        use_trash: bool = True,
    ) -> dict:
        agent = ControlWorkflowService.get_agent_or_raise(db, agent_name)
        if agent.status != AgentStatus.online:
            raise ValueError(f"`{agent.name}` is currently `{agent.status.value}`.")

        if ControlWorkflowService._agent_supports_capability(agent, "file_system"):
            try:
                command = ControlWorkflowService._run_command_and_wait(
                    db=db,
                    agent=agent,
                    user_id=user_id,
                    command_type="file_delete",
                    payload_json={"path": path, "use_trash": use_trash},
                    timeout_seconds=180,
                )
                return command.result_json or {}
            except ValueError as exc:
                if "unsupported control command" not in str(exc).lower():
                    raise

        return ControlWorkflowService._run_delete_fallback(db, agent, user_id, path, use_trash)

    @staticmethod
    def _run_storage_direct(
        db: Session,
        agent: Agent,
        user_id: str | None,
        path: str | None,
        top_n: int,
    ) -> dict:
        command = ControlWorkflowService._run_command_and_wait(
            db=db,
            agent=agent,
            user_id=user_id,
            command_type="storage_breakdown",
            payload_json={"path": path, "top_n": top_n},
            timeout_seconds=720,
        )
        return command.result_json or {}

    @staticmethod
    def _run_storage_fallback(
        db: Session,
        agent: Agent,
        user_id: str | None,
        path: str | None,
        top_n: int,
    ) -> dict:
        script = ControlWorkflowService._build_windows_storage_json_script(path, top_n)
        task = ControlWorkflowService._run_task_and_wait(
            db=db,
            agent=agent,
            user_id=user_id,
            title="Storage inspection",
            description=f"powershell:\n{script}",
            metadata_json={"execution_mode": "powershell", "command": script, "hidden_window": True},
            timeout_seconds=900,
        )
        try:
            return json.loads((task.result_text or "").strip() or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"Storage fallback returned invalid data: {exc}") from exc

    @staticmethod
    def _run_delete_fallback(
        db: Session,
        agent: Agent,
        user_id: str | None,
        path: str,
        use_trash: bool,
    ) -> dict:
        script = ControlWorkflowService._build_windows_delete_script(path, use_trash)
        task = ControlWorkflowService._run_task_and_wait(
            db=db,
            agent=agent,
            user_id=user_id,
            title="Delete path",
            description=f"powershell:\n{script}",
            metadata_json={"execution_mode": "powershell", "command": script, "hidden_window": True},
            timeout_seconds=240,
        )
        try:
            return json.loads((task.result_text or "").strip() or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"Delete fallback returned invalid data: {exc}") from exc

    @staticmethod
    def _run_command_and_wait(
        db: Session,
        agent: Agent,
        user_id: str | None,
        command_type: str,
        payload_json: dict,
        timeout_seconds: int,
    ):
        command = DeviceControlService.create_command(
            db=db,
            agent_name=agent.name,
            command_type=command_type,
            payload_json=payload_json,
            source="control_panel",
            created_by_user_id=user_id,
        )
        deadline = time.monotonic() + max(timeout_seconds, 5)
        while time.monotonic() < deadline:
            db.expire_all()
            current = DeviceControlService.get_command(db, command.command_id)
            if current and current.status in {DeviceCommandStatus.completed, DeviceCommandStatus.failed}:
                if current.status == DeviceCommandStatus.failed:
                    raise ValueError(current.error_text or f"Command `{command.command_id}` failed.")
                return current
            time.sleep(0.75)

        raise ValueError(f"Command `{command.command_id}` is still pending. Try again shortly.")

    @staticmethod
    def _run_task_and_wait(
        db: Session,
        agent: Agent,
        user_id: str | None,
        title: str,
        description: str,
        metadata_json: dict,
        timeout_seconds: int,
    ):
        task = TaskService.create_task(
            db=db,
            title=title,
            description=description,
            assigned_agent_name=agent.name,
            source="control_panel",
            command_type="compatibility-task",
            created_by_user_id=user_id,
            metadata_json=metadata_json,
        )
        deadline = time.monotonic() + max(timeout_seconds, 5)
        while time.monotonic() < deadline:
            db.expire_all()
            current = TaskService.get_task_by_task_id(db, task.task_id)
            if current and current.status in {TaskStatus.completed, TaskStatus.failed}:
                if current.status == TaskStatus.failed:
                    raise ValueError(current.error_text or f"Task `{task.task_id}` failed.")
                return current
            time.sleep(1.0)

        raise ValueError(f"Task `{task.task_id}` is still pending. Try again shortly.")

    @staticmethod
    def _agent_supports_capability(agent: Agent, capability: str) -> bool:
        capabilities = {str(item).strip().lower() for item in (agent.capabilities_json or [])}
        return capability.strip().lower() in capabilities

    @staticmethod
    def _should_use_storage_fallback(error_text: str | None) -> bool:
        lowered = str(error_text or "").lower()
        return "unsupported control command" in lowered or "storage_breakdown" in lowered

    @staticmethod
    def _escape_ps(value: str) -> str:
        return value.replace("'", "''")

    @staticmethod
    def _build_windows_storage_json_script(path: str | None, top_n: int) -> str:
        raw_path = (path or "").strip()
        if not raw_path or re.fullmatch(r"[A-Za-z]:\\?", raw_path):
            return ControlWorkflowService._build_windows_drive_overview_script(path, top_n)
        target_line = (
            f"$TargetPath = '{ControlWorkflowService._escape_ps(path)}'"
            if path
            else '$TargetPath = if ($env:SystemDrive) { "$($env:SystemDrive)\\" } else { "C:\\" }'
        )
        return f"""
$ErrorActionPreference = 'Stop'

function Format-Bytes([Int64]$Bytes) {{
    if ($Bytes -lt 1KB) {{ return "$Bytes B" }}
    if ($Bytes -lt 1MB) {{ return ('{{0:N1}} KB' -f ($Bytes / 1KB)) }}
    if ($Bytes -lt 1GB) {{ return ('{{0:N1}} MB' -f ($Bytes / 1MB)) }}
    if ($Bytes -lt 1TB) {{ return ('{{0:N1}} GB' -f ($Bytes / 1GB)) }}
    return ('{{0:N1}} TB' -f ($Bytes / 1TB))
}}

function Get-DirectorySize([string]$Path) {{
    $Total = 0L
    $ScannedFiles = 0
    Get-ChildItem -LiteralPath $Path -Recurse -Force -File -ErrorAction SilentlyContinue | ForEach-Object {{
        try {{
            $Total += [Int64]$_.Length
            $ScannedFiles += 1
        }} catch {{
        }}
    }}
    return @{{ size = $Total; files = $ScannedFiles }}
}}

{target_line}
$TopN = {top_n}
if (-not (Test-Path -LiteralPath $TargetPath)) {{
    throw "Path not found: $TargetPath"
}}

$ResolvedPath = (Resolve-Path -LiteralPath $TargetPath).Path
$RootTrimmed = $ResolvedPath.TrimEnd('\\')
$DriveRoot = [System.IO.Path]::GetPathRoot($ResolvedPath)
$Usage = $null
if ($DriveRoot) {{
    $DeviceId = $DriveRoot.TrimEnd('\\')
    $Usage = Get-CimInstance -ClassName Win32_LogicalDisk -Filter "DeviceID='$DeviceId'" -ErrorAction SilentlyContinue
}}

$IsDriveRoot = $DriveRoot -and [string]::Equals($RootTrimmed, $DriveRoot.TrimEnd('\\'), [System.StringComparison]::OrdinalIgnoreCase)
$SkippedEntries = 0
$ScannedFiles = 0
$ScannedDirs = 0
$EstimatedTotalBytes = 0L
$TopFolders = @()
$TopFiles = @()

if ($IsDriveRoot) {{
    $FolderRows = @()
    $FileRows = @()
    Get-ChildItem -LiteralPath $ResolvedPath -Force -ErrorAction SilentlyContinue | ForEach-Object {{
        try {{
            if ($_.PSIsContainer) {{
                $ScannedDirs += 1
                $Info = Get-DirectorySize $_.FullName
                $ScannedFiles += [Int64]$Info.files
                $EstimatedTotalBytes += [Int64]$Info.size
                $FolderRows += @{{ path = $_.FullName; size_bytes = [Int64]$Info.size; size_human = Format-Bytes([Int64]$Info.size) }}
            }} else {{
                $Size = [Int64]$_.Length
                $ScannedFiles += 1
                $EstimatedTotalBytes += $Size
                $FileRows += @{{ path = $_.FullName; size_bytes = $Size; size_human = Format-Bytes($Size) }}
            }}
        }} catch {{
            $SkippedEntries += 1
        }}
    }}
    $TopFolders = @($FolderRows | Sort-Object size_bytes -Descending | Select-Object -First $TopN)
    $TopFiles = @($FileRows | Sort-Object size_bytes -Descending | Select-Object -First $TopN)
}} else {{
    $AllFiles = @(Get-ChildItem -LiteralPath $ResolvedPath -Recurse -Force -File -ErrorAction SilentlyContinue)
    $AllDirs = @(Get-ChildItem -LiteralPath $ResolvedPath -Recurse -Force -Directory -ErrorAction SilentlyContinue)
    $DirSizes = @{{}}
    $ScannedDirs = $AllDirs.Count

    foreach ($File in $AllFiles) {{
        try {{
            $Size = [Int64]$File.Length
            $ScannedFiles += 1
            $EstimatedTotalBytes += $Size
            $Current = $File.DirectoryName
            while ($Current) {{
                if (-not $Current.StartsWith($RootTrimmed, [System.StringComparison]::OrdinalIgnoreCase)) {{ break }}
                if ($DirSizes.ContainsKey($Current)) {{ $DirSizes[$Current] += $Size }} else {{ $DirSizes[$Current] = $Size }}
                if ([string]::Equals($Current.TrimEnd('\\'), $RootTrimmed, [System.StringComparison]::OrdinalIgnoreCase)) {{ break }}
                $Parent = Split-Path -LiteralPath $Current -Parent
                if (-not $Parent -or [string]::Equals($Parent, $Current, [System.StringComparison]::OrdinalIgnoreCase)) {{ break }}
                $Current = $Parent
            }}
        }} catch {{
            $SkippedEntries += 1
        }}
    }}

    $TopFolders = @(
        $DirSizes.GetEnumerator() |
        Where-Object {{ -not [string]::Equals($_.Key.TrimEnd('\\'), $RootTrimmed, [System.StringComparison]::OrdinalIgnoreCase) }} |
        Sort-Object Value -Descending |
        Select-Object -First $TopN |
        ForEach-Object {{
            @{{ path = $_.Key; size_bytes = [Int64]$_.Value; size_human = Format-Bytes([Int64]$_.Value) }}
        }}
    )

    $TopFiles = @(
        $AllFiles |
        Sort-Object Length -Descending |
        Select-Object -First $TopN |
        ForEach-Object {{
            @{{ path = $_.FullName; size_bytes = [Int64]$_.Length; size_human = Format-Bytes([Int64]$_.Length) }}
        }}
    )
}}

$TopApps = @()
foreach ($Root in @("$($env:SystemDrive)\\Program Files", "$($env:SystemDrive)\\Program Files (x86)", "$($env:LOCALAPPDATA)\\Programs")) {{
    if (-not $Root -or -not (Test-Path -LiteralPath $Root)) {{ continue }}
    Get-ChildItem -LiteralPath $Root -Force -Directory -ErrorAction SilentlyContinue | ForEach-Object {{
        $Info = Get-DirectorySize $_.FullName
        $TopApps += @{{ name = $_.Name; path = $_.FullName; root = $Root; size_bytes = [Int64]$Info.size; size_human = Format-Bytes([Int64]$Info.size); scanned_files = [Int64]$Info.files }}
    }}
}}
$TopApps = @($TopApps | Sort-Object size_bytes -Descending | Select-Object -First $TopN)

$Output = @{{
    path = $ResolvedPath
    top_n = $TopN
    target_usage = if ($Usage -and $Usage.Size) {{
        @{{
            total_bytes = [Int64]$Usage.Size
            used_bytes = [Int64]$Usage.Size - [Int64]$Usage.FreeSpace
            free_bytes = [Int64]$Usage.FreeSpace
            percent = if ([Int64]$Usage.Size -gt 0) {{ [Math]::Round((([Int64]$Usage.Size - [Int64]$Usage.FreeSpace) / [Int64]$Usage.Size) * 100, 1) }} else {{ 0 }}
        }}
    }} else {{ @{{}} }}
    top_files = $TopFiles
    top_folders = $TopFolders
    top_apps = $TopApps
    scanned_files = $ScannedFiles
    scanned_dirs = $ScannedDirs
    skipped_entries = $SkippedEntries
    estimated_total_bytes = $EstimatedTotalBytes
    estimated_total_human = Format-Bytes($EstimatedTotalBytes)
    scan_mode = if ($IsDriveRoot) {{ 'shallow_root' }} else {{ 'deep' }}
    captured_at = [DateTime]::UtcNow.ToString('o')
}}

$Output | ConvertTo-Json -Depth 6 -Compress
""".strip()

    @staticmethod
    def _build_windows_drive_overview_script(path: str | None, top_n: int) -> str:
        target_line = (
            f"$TargetPath = '{ControlWorkflowService._escape_ps(path)}'"
            if path
            else '$TargetPath = if ($env:SystemDrive) { "$($env:SystemDrive)\\" } else { "C:\\" }'
        )
        return f"""
$ErrorActionPreference = 'Stop'

function Format-Bytes([Int64]$Bytes) {{
    if ($Bytes -lt 1KB) {{ return "$Bytes B" }}
    if ($Bytes -lt 1MB) {{ return ('{{0:N1}} KB' -f ($Bytes / 1KB)) }}
    if ($Bytes -lt 1GB) {{ return ('{{0:N1}} MB' -f ($Bytes / 1MB)) }}
    if ($Bytes -lt 1TB) {{ return ('{{0:N1}} GB' -f ($Bytes / 1GB)) }}
    return ('{{0:N1}} TB' -f ($Bytes / 1TB))
}}

function Get-InstalledApps([int]$Limit) {{
    $RegistryPaths = @(
        'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',
        'HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',
        'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*'
    )
    $Rows = foreach ($RegistryPath in $RegistryPaths) {{
        Get-ItemProperty -Path $RegistryPath -ErrorAction SilentlyContinue | ForEach-Object {{
            $DisplayName = $_.DisplayName
            $EstimatedSizeKb = $_.EstimatedSize
            if ($DisplayName -and $EstimatedSizeKb) {{
                [PSCustomObject]@{{
                    name = $DisplayName
                    path = $_.InstallLocation
                    size_bytes = [Int64]$EstimatedSizeKb * 1KB
                    size_human = Format-Bytes(([Int64]$EstimatedSizeKb * 1KB))
                }}
            }}
        }}
    }}
    @($Rows | Sort-Object size_bytes -Descending | Select-Object -First $Limit)
}}

{target_line}
$TopN = {top_n}
if (-not (Test-Path -LiteralPath $TargetPath)) {{
    throw "Path not found: $TargetPath"
}}

$ResolvedPath = (Resolve-Path -LiteralPath $TargetPath).Path
$DriveRoot = [System.IO.Path]::GetPathRoot($ResolvedPath)
$Usage = $null
if ($DriveRoot) {{
    $DeviceId = $DriveRoot.TrimEnd('\\')
    $Usage = Get-CimInstance -ClassName Win32_LogicalDisk -Filter "DeviceID='$DeviceId'" -ErrorAction SilentlyContinue
}}

$TopFiles = @(
    Get-ChildItem -LiteralPath $ResolvedPath -Force -File -ErrorAction SilentlyContinue |
    Sort-Object Length -Descending |
    Select-Object -First $TopN |
    ForEach-Object {{
        @{{ path = $_.FullName; size_bytes = [Int64]$_.Length; size_human = Format-Bytes([Int64]$_.Length) }}
    }}
)

$TopApps = Get-InstalledApps -Limit $TopN
$DirectDirs = @(Get-ChildItem -LiteralPath $ResolvedPath -Force -Directory -ErrorAction SilentlyContinue)
$DirectFiles = @(Get-ChildItem -LiteralPath $ResolvedPath -Force -File -ErrorAction SilentlyContinue)

$Output = @{{
    path = $ResolvedPath
    top_n = $TopN
    target_usage = if ($Usage -and $Usage.Size) {{
        @{{
            total_bytes = [Int64]$Usage.Size
            used_bytes = [Int64]$Usage.Size - [Int64]$Usage.FreeSpace
            free_bytes = [Int64]$Usage.FreeSpace
            percent = if ([Int64]$Usage.Size -gt 0) {{ [Math]::Round((([Int64]$Usage.Size - [Int64]$Usage.FreeSpace) / [Int64]$Usage.Size) * 100, 1) }} else {{ 0 }}
        }}
    }} else {{ @{{}} }}
    top_files = $TopFiles
    top_folders = @()
    top_apps = $TopApps
    scanned_files = $DirectFiles.Count
    scanned_dirs = $DirectDirs.Count
    skipped_entries = 0
    estimated_total_bytes = if ($Usage) {{ [Int64]$Usage.Size - [Int64]$Usage.FreeSpace }} else {{ 0L }}
    estimated_total_human = if ($Usage) {{ Format-Bytes(([Int64]$Usage.Size - [Int64]$Usage.FreeSpace)) }} else {{ '0 B' }}
    scan_mode = 'drive_overview'
    scan_note = 'Drive-root overview mode is faster. Inspect a narrower path like C:\\Users or Downloads for folder-level hotspots.'
    captured_at = [DateTime]::UtcNow.ToString('o')
}}

$Output | ConvertTo-Json -Depth 6 -Compress
""".strip()

    @staticmethod
    def _build_windows_delete_script(path: str, use_trash: bool) -> str:
        safe_path = ControlWorkflowService._escape_ps(path)
        delete_body = """
if ($UseTrash) {
    Add-Type -AssemblyName Microsoft.VisualBasic
    if (Test-Path -LiteralPath $Target -PathType Container) {
        [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory(
            $Target,
            [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,
            [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin
        )
    } else {
        [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile(
            $Target,
            [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,
            [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin
        )
    }
    $Method = 'recycle_bin'
} else {
    Remove-Item -LiteralPath $Target -Recurse -Force
    $Method = 'permanent_delete'
}
""".strip()
        return f"""
$ErrorActionPreference = 'Stop'
$Target = '{safe_path}'
$UseTrash = ${str(use_trash).lower()}
if (-not (Test-Path -LiteralPath $Target)) {{
    throw "Path not found: $Target"
}}
$ItemType = if (Test-Path -LiteralPath $Target -PathType Container) {{ 'directory' }} else {{ 'file' }}
{delete_body}
@{{
    ok = $true
    path = $Target
    deleted_type = $ItemType
    method = $Method
    deleted_at = [DateTime]::UtcNow.ToString('o')
}} | ConvertTo-Json -Depth 4 -Compress
""".strip()
