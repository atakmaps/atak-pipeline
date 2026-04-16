#define MyAppName "ATAK Pipeline"
#define MyAppVersion "1.0.0"
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

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"

[Icons]
Name: "{group}\ATAK Pipeline"; Filename: "{app}\ATAKPipeline.exe"
Name: "{autodesktop}\ATAK Pipeline"; Filename: "{app}\ATAKPipeline.exe"

[Run]
Filename: "{app}\ATAKPipeline.exe"; Description: "Launch ATAK Pipeline"; Flags: nowait postinstall
