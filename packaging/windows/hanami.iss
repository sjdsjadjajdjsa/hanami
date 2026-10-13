; Hanami's Windows installer (Inno Setup 6). Installs for the current user
; only, so it needs no admin rights. Built by .github/workflows/release.yml:
;
;   iscc /DVersion=0.1.2 /DSource=C:\full\path\to\dist\hanami packaging\windows\hanami.iss
;
; Source holds hanami.exe, README.md, GUIDE.md and LICENSE. Relative paths
; here count from this file's folder, so the default is the repo's dist\hanami.

#ifndef Version
  #define Version "0.0.0"
#endif
#ifndef Source
  #define Source "..\..\dist\hanami"
#endif

[Setup]
AppId={{7C1F4E5B-2D7A-4F49-9B5E-6A1D8C3E2F10}
AppName=Hanami
AppVersion={#Version}
AppVerName=Hanami {#Version}
AppPublisher=Hanami
AppPublisherURL=https://hanami.lilygrove.dev
AppSupportURL=https://github.com/sjdsjadjajdjsa/hanami
AppUpdatesURL=https://github.com/sjdsjadjajdjsa/hanami/releases
DefaultDirName={userpf}\Hanami
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
LicenseFile={#Source}\LICENSE
SetupIconFile=hanami.ico
UninstallDisplayIcon={app}\hanami.ico
UninstallDisplayName=Hanami
OutputDir=..\..
OutputBaseFilename=hanami-setup-x86_64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; A running Hanami is closed before its file is replaced.
CloseApplications=force
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startup"; Description: "Start Hanami when Windows starts"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "{#Source}\hanami.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Source}\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Source}\GUIDE.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Source}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "hanami.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\Hanami"; Filename: "{app}\hanami.exe"; IconFilename: "{app}\hanami.ico"; Comment: "Game launcher"
Name: "{userdesktop}\Hanami"; Filename: "{app}\hanami.exe"; IconFilename: "{app}\hanami.ico"; Tasks: desktopicon

[Registry]
; The Run key starts Hanami in the tray after sign-in; the second line
; removes it when the box is left unticked on a later install.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Hanami"; ValueData: """{app}\hanami.exe"" --hidden"; Flags: uninsdeletevalue; Tasks: startup
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "Hanami"; Flags: deletevalue; Tasks: not startup

[Run]
Filename: "{app}\hanami.exe"; Description: "Start Hanami now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM hanami.exe"; Flags: runhidden; RunOnceId: "QuitHanami"

[UninstallDelete]
; Hanami's cache (the once-a-day update check stamp). Settings in
; %APPDATA%\hanami stay, so a reinstall finds them.
Type: filesandordirs; Name: "{localappdata}\hanami"
