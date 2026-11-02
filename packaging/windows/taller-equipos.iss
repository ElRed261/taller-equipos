; Instalador de Windows del taller de equipos (Inno Setup 6).
;
; Se compila despues de PyInstaller, desde la raiz del repositorio:
;   iscc packaging\windows\taller-equipos.iss
; o con el script que hace las dos cosas:
;   packaging\windows\construir.ps1
;
; PyInstaller no compila para Windows desde Linux: este archivo tiene que ejecutarse
; en una maquina Windows (o en el runner windows-latest del flujo de trabajo).

#define NombreApp "Taller de equipos"
#define VersionArchivo "0.1.0"
#define Ejecutable "taller-equipos.exe"
#define OrigenPaquete "..\..\dist\taller-equipos"

[Setup]
AppId={{8E4C1F62-3B7A-4D51-9A0E-5C2D7F1B9A34}
AppName={#NombreApp}
AppVersion={#VersionArchivo}
AppPublisher=Taller de equipos
DefaultDirName={autopf}\Taller de equipos
DefaultGroupName={#NombreApp}
DisableProgramGroupPage=yes
OutputDir=..\..\dist
OutputBaseFilename=taller-equipos-{#VersionArchivo}-instalador
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; La aplicacion es de 64 bits: PySide6 no publica ruedas de 32.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Sin privilegios de administrador se instala en la carpeta del usuario. Un tecnico
; que no administra la PC tambien tiene que poder usar el programa.
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#Ejecutable}
; El paquete ya trae todo: no hace falta pedir nada durante la instalacion.

[Languages]
Name: "espanol"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"
Name: "inicio"; Description: "Iniciar con Windows"; GroupDescription: "Opciones:"; Flags: unchecked

[Files]
; El paquete completo de PyInstaller, con sus carpetas internas.
Source: "{#OrigenPaquete}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#NombreApp}"; Filename: "{app}\{#Ejecutable}"
Name: "{group}\Desinstalar {#NombreApp}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#NombreApp}"; Filename: "{app}\{#Ejecutable}"; Tasks: escritorio
Name: "{userstartup}\{#NombreApp}"; Filename: "{app}\{#Ejecutable}"; Tasks: inicio

[Run]
; Se abre al terminar para que la primera vez se configure sola: marca, conexion y
; cuenta administradora. Si falla, el instalador no se cae.
Filename: "{app}\{#Ejecutable}"; Description: "Abrir {#NombreApp}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Nada de la configuracion del usuario ni de la base: el instalador solo quita
; el programa. Lo que la persona configuro queda en su perfil.
Type: filesandordirs; Name: "{app}"
