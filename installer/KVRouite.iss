; ===== KVRouite — Stable ISS (no Code) =====

#define MyAppName      "KVRouite"
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

; Quelle: innerer PyInstaller-Ordner
#ifndef MyDistDir
  #define MyDistDir "dist\\KVRouite_" + MyAppVersion + "\\KVRouite_" + MyAppVersion
#endif

; Installer-Icon optional absichern
#ifndef MyIconFile
  #define MyIconFile AddBackslash(MyDistDir) + "icon\\icon_icon.ico"
#endif

; Agreement (EULA/Disclaimer) – Nutzer muss zustimmen
#ifndef MyEula
  #define MyEula AddBackslash(SourcePath) + "AGREEMENT.txt"
#endif

[Setup]
AppId={{C4E3D0F1-7E94-45F7-91D4-A32AB4E9KVR}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=ridewithoutstomach
AppPublisherURL=https://github.com/ridewithoutstomach/KVRouite

DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=no
DisableProgramGroupPage=no

; Ausgabe nach dist\<Version>
OutputDir={#SourcePath}\..\dist\{#MyAppVersion}
OutputBaseFilename=KVRouite_Setup_v{#MyAppVersion}_Win_x64

WizardStyle=modern
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
PrivilegesRequired=admin
SetupIconFile={#MyIconFile}
UninstallDisplayIcon={app}\KVRouite.exe
ChangesAssociations=yes

; Hilfreich, aber ungefährlich
UsePreviousAppDir=yes
UsePreviousLanguage=yes
UsePreviousTasks=yes

; Nutzer muss zustimmen (zeigt AGREEMENT.txt)
LicenseFile={#MyEula}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; Nimmt ALLES (inkl. ol.css, ol.js, map_page.html, icon/, _internal/, LICENSE)
Source: "{#MyDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Vor der Installation Zielordner vollständig leeren → keine Altdateien
Type: filesandordirs; Name: "{app}\*"

[Icons]
Name: "{group}\KVRouite"; Filename: "{app}\KVRouite.exe"
Name: "{commondesktop}\KVRouite"; Filename: "{app}\KVRouite.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons"; Flags: unchecked

[Registry]
; Dateizuordnung .kvrproj → KVRouite
Root: HKCR; Subkey: ".kvrproj"; ValueType: string; ValueData: "KVRouite.Project"; Flags: uninsdeletevalue
Root: HKCR; Subkey: "KVRouite.Project"; ValueType: string; ValueData: "KVRouite Project File"; Flags: uninsdeletekey
Root: HKCR; Subkey: "KVRouite.Project\DefaultIcon"; ValueType: string; ValueData: "{app}\KVRouite.exe,0"
Root: HKCR; Subkey: "KVRouite.Project\shell\open\command"; ValueType: string; ValueData: """{app}\KVRouite.exe"" ""%1"""

[Run]
Filename: "{app}\KVRouite.exe"; Description: "Launch KVRouite"; Flags: postinstall nowait skipifsilent

[InstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then begin
    if DirExists(ExpandConstant('{app}')) then begin
      Log('Cleaning target dir: ' + ExpandConstant('{app}'));
      if not DelTree(ExpandConstant('{app}'), True, True, True) then
        MsgBox('Could not clean the target folder: ' + #13#10 + ExpandConstant('{app}'),
               mbError, MB_OK);
    end;
  end;
end;