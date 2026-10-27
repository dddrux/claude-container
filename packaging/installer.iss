; Inno Setup 6 — instalador x64. Compilar com: ISCC /DAppVersion=1.0.0 packaging\installer.iss
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6B1D4C7E-2A53-4F0B-9C3A-C1A0DE50A117}
AppName=Claude Containers
AppVersion={#AppVersion}
DefaultDirName={autopf}\Claude Containers
DefaultGroupName=Claude Containers
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\claude-containers.exe
OutputDir=..\dist
OutputBaseFilename=Claude-Containers-{#AppVersion}-Setup-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "..\dist\claude-containers\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion createallsubdirs

[Icons]
Name: "{autoprograms}\Claude Containers"; Filename: "{app}\claude-containers.exe"; IconFilename: "{app}\claude-containers.exe"
Name: "{autodesktop}\Claude Containers"; Filename: "{app}\claude-containers.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\claude-containers.exe"; Description: "Abrir Claude Containers"; Flags: nowait postinstall skipifsilent
