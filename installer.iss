; Instalador de Windows (Inno Setup 6) de TalNumStack.
;
; La version NO se escribe aqui: la inyecta scripts/build_installer_win.bat
; (y el workflow de GitHub) desde TALNUMSTACK_VERSION en lang.py:
;     iscc /DAppVersion=3.9 /DOutputName=TalNumStack_39_Win_x86_64_Installer installer.iss
;
; Requiere dist\TalNumStack.exe (scripts\build_app_win.bat).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef OutputName
  #define OutputName "TalNumStack_Win_x86_64_Installer"
#endif

#define AppName "TalNumStack"
#define AppExe "TalNumStack.exe"

[Setup]
; AppId fijo: permite actualizar sobre la version anterior y que el
; desinstalador sea el mismo entre versiones. NO cambiar.
AppId={{7C4A9E52-3B7D-4F18-9A61-2D8BE1C5A730}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppName}
AppPublisherURL=https://github.com/japr99/tns_p
AppSupportURL=https://github.com/japr99/tns_p
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=dist-installers
OutputBaseFilename={#OutputName}
SetupIconFile=TalNumStack.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Instala en C:\Archivos de programa (pide permisos de administrador).
PrivilegesRequired=admin
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
; La app guarda sus preferencias en %LOCALAPPDATA%, nunca junto al .exe.
CloseApplications=yes
RestartApplications=no
; Refresca la caché de iconos de Explorer al registrar la asociacion .tns.
ChangesAssociations=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "catalan"; MessagesFile: "compiler:Languages\Catalan.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "installerwin\INSTALAR_WINDOWS.txt"; DestDir: "{app}"; Flags: ignoreversion

[Registry]
; Asociacion .tns a nivel de maquina: el icono esta disponible desde la
; instalacion, sin esperar al primer arranque (fileassoc_windows.py sigue
; haciendo la parte por usuario en HKCU como auto-reparacion).
Root: HKLM; Subkey: "Software\Classes\.tns"; ValueType: string; ValueName: ""; ValueData: "TalNumStack.tns"; Flags: uninsdeletevalue
Root: HKLM; Subkey: "Software\Classes\TalNumStack.tns"; ValueType: string; ValueName: ""; ValueData: "TalNumStack Trabajo"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\TalNumStack.tns\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"",0"
Root: HKLM; Subkey: "Software\Classes\TalNumStack.tns\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Instrucciones de instalacion"; Filename: "{app}\INSTALAR_WINDOWS.txt"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\INSTALAR_WINDOWS.txt"; Description: "Ver instrucciones de instalacion"; Flags: postinstall shellexec unchecked
