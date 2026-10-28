; Inno Setup script for Sahm Download Manager
#define AppName "Sahm Download Manager"
#define AppVersion "1.1.1"

[Setup]
AppId={{6B2D3C1E-5A8F-4D7B-9E21-5A1C9F0D7E4A}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Noni
DefaultDirName={autopf}\Sahm
DefaultGroupName=Sahm
OutputDir=dist
OutputBaseFilename=Sahm-Setup
SetupIconFile=app\assets\icon.ico
UninstallDisplayIcon={app}\Sahm.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startup"; Description: "Start Sahm when Windows starts"; GroupDescription: "Other:"

[Files]
Source: "dist\Sahm\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "extension\*"; DestDir: "{app}\extension"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Sahm"; Filename: "{app}\Sahm.exe"
Name: "{group}\Browser extension folder"; Filename: "{app}\extension"
Name: "{group}\Uninstall Sahm"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Sahm"; Filename: "{app}\Sahm.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
  ValueName: "Sahm"; ValueData: """{app}\Sahm.exe"" --minimized"; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\Sahm.exe"; Description: "{cm:LaunchProgram,Sahm}"; Flags: nowait postinstall skipifsilent
