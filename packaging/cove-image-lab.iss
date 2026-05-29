; Inno Setup script for Cove Image Lab — produces Setup.exe.
;
; Expects packaging/cove-image-lab.spec (--onedir) to have already
; produced dist\cove-image-lab\ via PyInstaller. The release workflow
; runs PyInstaller, generates a .ico from the PNG, then invokes ISCC
; against this script.
;
; AppVersion / SourceDir / OutputDir can be overridden from the command
; line: `iscc /DAppVersion=1.0.1 /DSourceDir=...`.

#define AppName "Cove Image Lab"
#define AppPublisher "Sin213"
#define AppExeName "cove-image-lab.exe"
#define AppId "{{5C8E4FB2-4A7B-4C9E-B3F1-A0B1C2D3E4F5}}"

#ifndef AppVersion
  #define AppVersion "1.1.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\cove-image-lab"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://github.com/Sin213/cove-image-lab
AppSupportURL=https://github.com/Sin213/cove-image-lab/issues
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir={#OutputDir}
OutputBaseFilename=Cove-Image-Lab-Setup-{#AppVersion}
SetupIconFile=..\src\cove_image_lab\assets\cove_icon.ico
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
UninstallDisplayIcon={app}\{#AppExeName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
