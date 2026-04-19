#define MyAppName "ATAK Pipeline"
#define MyAppVersion "0.2.5"
#define MyAppExeName "ATAKPipeline.exe"

[Setup]
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=installer-dist
OutputBaseFilename=ATAKPipelineSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"

[Icons]
Name: "{group}\ATAK Pipeline"; Filename: "{app}\ATAKPipeline.exe"; WorkingDir: "{app}"
Name: "{userprograms}\ATAK Pipeline"; Filename: "{app}\ATAKPipeline.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\ATAK Pipeline"; Filename: "{app}\ATAKPipeline.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\ATAKPipeline.exe"; Description: "Launch ATAK Pipeline"; Flags: nowait postinstall
