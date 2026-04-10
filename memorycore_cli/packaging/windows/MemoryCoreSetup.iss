#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{8C4E9A74-4C6C-4B2A-8F2E-1CF3DA8724C1}
AppName=MemoryCore
AppVersion={#AppVersion}
AppPublisher=FitClaw
DefaultDirName={localappdata}\Programs\MemoryCore
DefaultGroupName=MemoryCore
DisableProgramGroupPage=yes
OutputDir=..\..\dist
OutputBaseFilename=MemoryCoreSetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ChangesEnvironment=yes
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\..\dist\memorycore-bin.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\dist\memorycore.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\dist\hey.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\dist\*.cmd"; DestDir: "{app}"; Flags: ignoreversion; Excludes: "memorycore.cmd,hey.cmd,Install MemoryCore.cmd"
Source: "..\..\dist\README.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\MemoryCore README"; Filename: "notepad.exe"; Parameters: """{app}\README.txt"""
Name: "{group}\Uninstall MemoryCore"; Filename: "{uninstallexe}"

[Code]
function NeedsAddPath(PathValue: string): Boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', OrigPath) then
    OrigPath := '';
  Result := Pos(';' + Uppercase(PathValue) + ';', ';' + Uppercase(StringChangeEx(OrigPath, '"', '', True)) + ';') = 0;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  OrigPath: string;
begin
  if CurStep = ssPostInstall then
  begin
    if not RegQueryStringValue(HKCU, 'Environment', 'Path', OrigPath) then
      OrigPath := '';

    if NeedsAddPath(ExpandConstant('{app}')) then
    begin
      if (OrigPath <> '') and (Copy(OrigPath, Length(OrigPath), 1) <> ';') then
        OrigPath := OrigPath + ';';
      OrigPath := OrigPath + ExpandConstant('{app}');
      RegWriteExpandStringValue(HKCU, 'Environment', 'Path', OrigPath);
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  PathValue: string;
  AppDir: string;
  NewPath: string;
  Parts: TArrayOfString;
  Index: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    AppDir := Uppercase(ExpandConstant('{app}'));
    if RegQueryStringValue(HKCU, 'Environment', 'Path', PathValue) then
    begin
      Parts := SplitString(PathValue, ';');
      NewPath := '';
      for Index := 0 to GetArrayLength(Parts) - 1 do
      begin
        if Trim(Uppercase(RemoveQuotes(Parts[Index]))) <> AppDir then
        begin
          if NewPath <> '' then
            NewPath := NewPath + ';';
          NewPath := NewPath + Parts[Index];
        end;
      end;
      RegWriteExpandStringValue(HKCU, 'Environment', 'Path', NewPath);
    end;
  end;
end;
