# Configuración de pyside6-deploy (Nuitka) del taller de equipos.
#
# Este spec lo genera pyside6-deploy --init y el build lo consume con -c.
# está en inglés porque es un artefacto de compilación.
#
# Reglas del proyecto:
#   - standalone, nunca onefile: la ventana tiene que aparecer al instante y un
#     autoextraíble en /tmp por cada doble clic es exactamente lo contrario.
#   - Los datos (migraciones y assets) viajan junto al ejecutable; ver
#     packaging/qtifw/construir.sh, que es quien los copia.
#
[Config]
# Entry principal de la app. pyside6-deploy compila en la plataforma donde corre.
application = src/taller/main.py
name = taller-equipos
mode = standalone

# Módulos del proyecto que nuitka no ve por imports dinámicos.
extra_modules =
    taller
    alembic
    sqlalchemy
    psycopg
    pydantic
    pydantic_settings
    argon2

# Directorios que no viajan en el paquete (están en el repo, no en el binario).
extra_ignore_dirs =
    tests
    migrations
    docs
    odd
    packaging
    dist
