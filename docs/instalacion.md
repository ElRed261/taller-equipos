# Instalar y migrar

Qué se entrega, cómo se instala en cada sistema y cómo se lleva la base al servidor.

## Qué es «el instalador»

El programa se empaqueta con PyInstaller en **modo carpeta**: un directorio con el
ejecutable y todo lo que necesita, sin requerir Python en la máquina. Alrededor de ese
directorio, cada sistema tiene su instalador:

| Sistema | Artefacto | Qué hace |
| --- | --- | --- |
| Linux | `taller-equipos-linux.tar.gz` | trae el paquete y `instalar.sh`, que copia, crea el lanzador y la entrada del menú |
| Windows | `taller-equipos-<versión>-instalador.exe` | instalador de Inno Setup: accesos directos, desinstalador y arranque opcional con Windows |

Los dos se construyen en el flujo de trabajo
`.github/workflows/instaladores.yml`, cada uno en su runner, porque **PyInstaller no
compila para otro sistema**: el binario corre en el sistema donde se ejecuta.

```bash
# a mano, desde GitHub
gh workflow run instaladores.yml

# o empujando una etiqueta
git tag v0.1.0 && git push origin v0.1.0
```

Los artefactos quedan en la corrida, disponibles por 30 días.

## Linux

```bash
scripts/empaquetar.sh                    # arma dist/taller-equipos (unos 250 MB)
packaging/linux/instalar.sh              # instala para el usuario actual
sudo packaging/linux/instalar.sh         # instala para todo el sistema
packaging/linux/instalar.sh --prefijo /opt/taller   # elige dónde
```

Sin `--prefijo`, instala en `/usr/local` si se corre como administrador y en
`~/.local` si no: un instalador que siempre exige `sudo` no sirve en la PC de un
técnico que no administra la máquina.

Deja el programa en `<prefijo>/lib/taller-equipos`, un lanzador en
`<prefijo>/bin/taller-equipos`, la entrada del menú de aplicaciones, el icono y un
desinstalador. Se puede volver a correr sobre una instalación existente: reemplaza la
versión anterior y **no toca la configuración del usuario** ni la base.

Para desinstalar:

```bash
<prefijo>/share/taller-equipos/desinstalar.sh "<prefijo>/lib/taller-equipos" "<prefijo>"
```

El instalador se niega a instalar un paquete que contenga la marca institucional: la
marca se configura en la aplicación, no se empaqueta.

## Windows

En una máquina Windows con [uv](https://docs.astral.sh/uv/) e Inno Setup 6:

```powershell
winget install JRSoftware.InnoSetup
powershell -ExecutionPolicy Bypass -File packaging\windows\construir.ps1
```

El script empaqueta, verifica que el binario responda `--version`, comprueba que el
paquete no lleve la marca institucional y compila el instalador con Inno Setup.

El instalador de Windows:

- instala en `Archivos de programa` si hay permisos, o en la carpeta del usuario si no;
- ofrece acceso directo en el escritorio y arranque con Windows (los dos opcionales);
- abre el programa al terminar, para que la primera vez se configure solo: marca,
  conexión y cuenta administradora;
- incluye desinstalador, y **no borra la configuración personal** ni toca la base.

## Desinstalar por completo

### Linux

Primero, mirar qué hay instalado sin borrar nada — el programa puede estar en
`~/.local` (instalación de usuario) o en `/usr/local` (instalación con `sudo`):

```bash
scripts/desinstalar.sh                 # solo muestra lo que encontró
scripts/desinstalar.sh --si            # lo borra
```

Si lo instalaste con `sudo`, el lanzador en `/usr/local/bin` es de `root` y el
desinstalador necesita `sudo`:

```bash
sudo scripts/desinstalar.sh --si --prefijo /usr/local
```

Y si preferís el desinstalador que dejó la propia instalación:

```bash
# quita el programa y deja la configuración
<prefijo>/share/taller-equipos/desinstalar.sh

# quita el programa Y la configuración guardada
<prefijo>/share/taller-equipos/desinstalar.sh --con-configuracion
```

El desinstalador **nunca toca la base de datos**: los datos no son del programa.
Borra el programa, el lanzador, la entrada del menú y el icono. Con
`--con-configuracion` borra además `~/.config/Taller de equipos/` (nombre, logo,
conexión guardada y el ajuste del ingreso).

### Windows

Configuración → Aplicaciones → *Taller de equipos* → Desinstalar. Después, si querés
borrar también lo que la persona configuró:

```powershell
Remove-Item -Recurse "$env:APPDATA\Taller de equipos"
```

### Lo que queda y hay que decidir aparte

| Qué | Dónde | Cómo se quita |
| --- | --- | --- |
| La base de datos y sus roles | El servidor PostgreSQL | `DROP DATABASE taller_dev; DROP ROLE taller_app, taller_ro;` — **borra los datos** |
| El `.env` del proyecto | Solo en desarrollo | `rm .env` |
| La carpeta de construcción | `dist/`, `build/` | `rm -rf dist build` |
| El servicio que arranca PostgreSQL | `brew services` | `brew services stop postgresql@18` |

Ninguno de esos pasos es parte de «desinstalar el programa»: son decisiones sobre
datos e infraestructura, y por eso no los hace un desinstalador solo.

## Qué no hace ningún instalador

- **No instala PostgreSQL.** El servidor de base de datos es infraestructura: se
  instala y se asegura una vez, siguiendo `docs/seguridad.md`.
- **No lleva la marca de la organización.** Nombre, logo y descripción se eligen en
  el asistente de la primera ejecución y quedan en la carpeta del usuario.
- **No migra los datos.** Eso es el paquete de migración, abajo.

## Migrar la base a otro servidor

```bash
scripts/empaquetar_migracion.sh
```

Deja una carpeta con fecha en `~/respaldos-taller/` con todo lo necesario y, antes de
terminar, **restaura el paquete en una base descartable y compara los conteos** contra
el origen: un paquete que no se probó restaurar no es un respaldo.

| Archivo | Qué es |
| --- | --- |
| `taller_dev.dump` | volcado completo en formato custom (esquema y datos) |
| `indice-del-volcado.txt` | el contenido del volcado tal como lo ve `pg_restore --list` |
| `roles.sql` | todos los roles del clúster, con sus contraseñas hasheadas |
| `manifiesto.txt` | versiones, codificación, extensiones y conteos del momento |
| `LEEME-MIGRACION.md` | qué hacer en el servidor, paso por paso |
| `SUMAS.sha256` | para comprobar que nada se corrompió al copiar |

La carpeta queda en `0700` y los archivos en `0600` porque `roles.sql` lleva hashes de
contraseña. **No apliques `roles.sql` tal cual en producción**: trae el superusuario de
la máquina de desarrollo. El LEEME explica cómo crear solo los dos roles que la
aplicación necesita.

Resumen del procedimiento (el detalle está en el LEEME del paquete y en
`docs/recuperacion.md`):

1. En el servidor: crear los roles `taller_app` y `taller_ro`, la base `taller_dev`
   con `UTF8`, y las extensiones `pg_trgm` y `unaccent`.
2. Copiar el paquete y comprobar las sumas con `sha256sum -c SUMAS.sha256`.
3. `pg_restore --no-owner --no-privileges -d taller_dev taller_dev.dump`.
4. Comparar los conteos con `manifiesto.txt` **antes** de abrir el sistema.
5. Apuntar la aplicación al servidor desde Configuración → Sistema.
6. Cerrar la puerta: `pg_hba` por base y rol, `listen_addresses` en la interfaz
   interna, TLS, respaldos por cron y `archive_mode` para PITR.

Antes de mover el paquete, cifralo con una frase que solo vos tengas:

```bash
tar -czf - ~/respaldos-taller/migracion-*/ | gpg --symmetric --output migracion.tar.gz.gpg
```
