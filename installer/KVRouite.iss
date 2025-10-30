; ===== KVRouite — Installer (Info-Seite & Cleaning-Hinweis) =====

#define MyAppName        "KVRouite"
#define MyAppPublisher   "ridewithoutstomach"
#define MyAppURL         "https://github.com/ridewithoutstomach/KVRouite"

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

; Quelle: innerer PyInstaller-Ordner dist\KVRouite_<ver>\KVRouite_<ver>
#ifndef MyDistDir
  #define MyDistDir "dist\\KVRouite_" + MyAppVersion + "\\KVRouite_" + MyAppVersion
#endif

; Installer-Icon (Fallback, dein Builder kann /DMyIconFile übergeben)
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
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}

; Ausgabe: dist\<Version>\
OutputDir={#SourcePath}\..\dist\{#MyAppVersion}
; Moderner Dateiname:
OutputBaseFilename=KVRouite_v{#MyAppVersion}_Win_x64_Installer

WizardStyle=modern
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
PrivilegesRequired=admin
SetupIconFile={#MyIconFile}
UninstallDisplayIcon={app}\KVRouite.exe
ChangesAssociations=yes
DirExistsWarning=yes

; Komfort: Vorbelegungen merken
UsePreviousAppDir=yes
UsePreviousLanguage=yes
UsePreviousTasks=yes

; Agreement anzeigen (I accept…)
LicenseFile={#MyEula}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons"; Flags: unchecked

[Files]
; Nimmt ALLES aus deinem PyInstaller-Ziel (inkl. ol.css, ol.js, map_page.html, icon/, _internal/, LICENSE)
Source: "{#MyDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\KVRouite"; Filename: "{app}\KVRouite.exe"
Name: "{commondesktop}\KVRouite"; Filename: "{app}\KVRouite.exe"; Tasks: desktopicon

[Registry]
; Dateizuordnung .kvrproj → KVRouite
Root: HKCR; Subkey: ".kvrproj"; ValueType: string; ValueData: "KVRouite.Project"; Flags: uninsdeletevalue
Root: HKCR; Subkey: "KVRouite.Project"; ValueType: string; ValueData: "KVRouite Project File"; Flags: uninsdeletekey
Root: HKCR; Subkey: "KVRouite.Project\DefaultIcon"; ValueType: string; ValueData: "{app}\KVRouite.exe,0"
Root: HKCR; Subkey: "KVRouite.Project\shell\open\command"; ValueType: string; ValueData: """{app}\KVRouite.exe"" ""%1"""

[Run]
Filename: "{app}\KVRouite.exe"; Description: "Launch KVRouite"; Flags: postinstall nowait skipifsilent

[Code]
var
  CleanInfoPage: TOutputMsgWizardPage;
  CleanInfoPageCreated: Boolean;

procedure CurPageChanged(CurPageID: Integer);
var
  Msg: string;
begin
  { Info-Seite dynamisch NACH "Select Tasks" und VOR "Ready to Install" einhängen,
    nachdem der Nutzer den Zielordner gewählt hat. }
  if (CurPageID = wpSelectTasks) and (not CleanInfoPageCreated) then
  begin
    if DirExists(WizardDirValue) then
    begin
      Msg :=
        'An existing KVRouite installation was found:' + #13#10 +
        WizardDirValue + #13#10#13#10 +
        'Setup will remove the contents of this folder before installing the new version.' + #13#10 +
        'Click Next to continue.';
      CleanInfoPage :=
        CreateOutputMsgPage(
          wpSelectTasks,                    { nach Tasks, vor Ready }
          'Cleanup of previous installation',
          'Existing installation detected',
          Msg
        );
      CleanInfoPageCreated := True;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    { Sichtbarer Hinweis während des Löschens/Kopierens }
    WizardForm.StatusLabel.Caption := 'Cleaning previous installation...';
    WizardForm.StatusLabel.Visible := True;
    WizardForm.ProgressGauge.Style := npbstMarquee;
    WizardForm.ProgressGauge.Visible := True;

    { Zielordner vollständig löschen (kompatibel, ersetzt frühere [InstallDelete]-Sektion) }
    if DirExists(WizardDirValue) then
    begin
      if not DelTree(WizardDirValue, True, True, True) then
        MsgBox('Could not clean the target folder:' + #13#10 + WizardDirValue,
               mbError, MB_OK);
    end;

    { Zielordner für den folgenden Kopiervorgang sicherstellen }
    if not DirExists(WizardDirValue) then
      CreateDir(WizardDirValue);
  end;
end;
