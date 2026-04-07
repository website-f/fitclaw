#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{0B12B96A-0F0E-4E15-A403-54E6D7DF9487}
AppName=Personal AI Ops Agent
AppVersion={#AppVersion}
AppPublisher=Personal AI Ops
DefaultDirName={autopf}\PersonalAIOpsAgent
DefaultGroupName=Personal AI Ops Agent
DisableProgramGroupPage=yes
OutputDir=..\..\dist
OutputBaseFilename=PersonalAIOpsAgentSetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\..\dist\PersonalAIOpsAgent.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Personal AI Ops Agent"; Filename: "{app}\PersonalAIOpsAgent.exe"
Name: "{group}\Uninstall Personal AI Ops Agent"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\PersonalAIOpsAgent.exe"; Description: "Open Personal AI Ops Agent setup"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\PersonalAIOpsAgent"

