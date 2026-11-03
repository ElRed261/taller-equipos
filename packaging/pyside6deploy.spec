[app]
title = taller-equipos

# la raíz del proyecto = el entry point abre la app y el resto de taller/
# llega por imports normales con --follow-imports.
project_dir = ..
input_file = /home/stward/Proyectos/taller-equipos/src/taller/main.py

# path to the project file relative to project_dir
project_file = 

# directorio donde pyside6-deploy deja el resultado
exec_directory = dist

# icono del proyecto = lo genera scripts/generar_icono.py; genérico, sin marca.
icon = packaging/icono.png

[python]
packages = Nuitka

[qt]

# path to required qml files. comma separated
qml_files = 

# excluded qml plugin binaries
excluded_qml_plugins = 
modules = Core,DBus,Gui,Svg,Widgets
plugins = accessiblebridge,egldeviceintegrations,generic,iconengines,imageformats,platforminputcontexts,platforms,platformthemes,styles,xcbglintegrations

[nuitka]

# standalone = carpeta con el ejecutable y sus dependencias; arranca al
# instante, sin autoextraerse en cada doble clic (medido = onefile tardaba
# segundos en aparecer en las máquinas del taller).
mode = standalone

# info de los consultorios de nuitka extra = sin traducciones de Qt (ahora son
# usadas) y no las dlls intermedias.
extra_args = --quiet --noinclude-qt-translations --include-qt-plugins=platforminputcontexts

