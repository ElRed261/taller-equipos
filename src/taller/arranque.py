"""Configuración de arranque: dónde vive y cómo se guarda.

Una aplicación empaquetada no puede pedirle al usuario que edite un ``.env``. La
primera vez que se abre pregunta lo mínimo —la marca de la organización y la
conexión— y lo guarda en la carpeta de configuración del usuario, que es el único
lugar escribible cuando el programa está instalado en ``/opt`` o en ``C:\\Program
Files``.

El logo elegido se **copia** a esa carpeta: si el usuario después mueve o borra la
imagen original, la aplicación sigue mostrando su marca.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

NOMBRE_ARCHIVO: Final = "config.json"
NOMBRE_LOGO: Final = "logo.png"
NOMBRE_APLICACION: Final = "Taller de equipos"

#: Carpetas donde se busca el directorio de migraciones.
DIRECTORIOS_MIGRACIONES: Final = ("migrations",)


def carpeta_configuracion() -> Path:
    """The per-user folder for the application's settings.

    Se calcula sin Qt a propósito: ``settings.py`` llama acá desde procesos sin
    interfaz (Alembic, los scripts de mantenimiento) y ``QStandardPaths`` no es
    fiable sin una aplicación creada.
    """
    desde_entorno = os.environ.get("TALLER_CONFIG_DIR")
    if desde_entorno:
        carpeta = Path(desde_entorno).expanduser()
    elif os.name == "nt":
        raiz = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        carpeta = raiz / NOMBRE_APLICACION
    elif sys.platform == "darwin":
        carpeta = Path.home() / "Library" / "Application Support" / NOMBRE_APLICACION
    else:
        raiz = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        carpeta = raiz / NOMBRE_APLICACION
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def carpeta_migraciones() -> Path:
    """Locate the Alembic migrations, in the repo or inside the bundle."""
    candidatas = []
    empaquetada = getattr(sys, "_MEIPASS", None)
    if empaquetada:
        candidatas.append(Path(empaquetada) / "migrations")
    raiz = Path(__file__).resolve().parent.parent.parent
    candidatas.extend(raiz / nombre for nombre in DIRECTORIOS_MIGRACIONES)
    for candidata in candidatas:
        if (candidata / "env.py").is_file():
            return candidata
    raise FileNotFoundError(
        "no se encontró el directorio de migraciones; "
        f"se buscó en: {', '.join(str(c) for c in candidatas)}"
    )


def aplicar_migraciones(database_url: str) -> None:
    """Create or update the schema for the given URL.

    Va por Alembic y no por ``metadata.create_all`` porque el esquema incluye una
    vista y dos triggers que sólo existen en la migración.
    """
    from alembic import command
    from alembic.config import Config

    configuracion = Config()
    configuracion.set_main_option("script_location", str(carpeta_migraciones()))
    configuracion.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(configuracion, "head")


def _url_de_mantenimiento(url: str) -> str:
    """La misma conexión, pero a la base ``postgres``: sirve para ver qué hay."""
    from sqlalchemy.engine import make_url

    return make_url(url).set(database="postgres").render_as_string(hide_password=False)


def preparar_base(url: str) -> tuple[bool, str]:
    """Deja la base lista para usar, o explica por qué no puede.

    Al abrir el programa: si la base no existe se crea (cuando el rol tiene
    permiso), y si existe se le aplican las migraciones que falten. Así una
    instalación nueva no pide ningún paso en la consola, y una que ya funcionaba
    solo se conecta.

    Devuelve ``(True, "")`` cuando quedó lista. Nunca levanta: el llamador muestra
    el mensaje tal cual.
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    try:
        destino = make_url(url)
    except Exception as error:  # noqa: BLE001 - una URL inválida se cuenta tal cual
        return False, f"La dirección de la base no es válida: {error}"

    nombre = destino.database or ""
    usuario = destino.username or "el usuario de la aplicación"
    motor = None
    try:
        motor = create_engine(_url_de_mantenimiento(url), isolation_level="AUTOCOMMIT")
        with motor.connect() as conexion:
            existe = conexion.execute(
                text("select 1 from pg_database where datname = :nombre"),
                {"nombre": nombre},
            ).first()
            crear = existe is None
            if crear:
                try:
                    conexion.execute(
                        text(f'create database "{nombre}" owner "{usuario}"')
                    )
                except Exception as error:  # noqa: BLE001
                    # Sin CREATEDB no se puede, y está bien que no se pueda: crear
                    # bases es del administrador, no de la aplicación.
                    motivo = re.sub(
                        r"^\((?:[\w.]+\.)?\w+\)\s*", "", str(error).splitlines()[0]
                    )
                    return False, (
                        f"La base «{nombre}» no existe y «{usuario}» no puede crearla "
                        f"({motivo}).\n\nUn administrador tiene que ejecutar una vez:\n\n"
                        f'    CREATE DATABASE "{nombre}" OWNER "{usuario}";\n\n'
                        "Después volvé a abrir el programa: las tablas se crean solas."
                    )
    except Exception as error:  # noqa: BLE001
        mensaje = str(error).splitlines()[0]
        if "does not exist" in mensaje and nombre:
            return False, (
                f"La base «{nombre}» no existe y no se pudo crear. Pedile a un "
                f"administrador:\n\n    CREATE DATABASE \"{nombre}\" OWNER \"{usuario}\";"
            )
        return False, f"No se pudo conectar con la base:\n\n{mensaje}"
    finally:
        if motor is not None:
            with contextlib.suppress(Exception):
                motor.dispose()

    try:
        aplicar_migraciones(url)
    except Exception as error:  # noqa: BLE001
        mensaje = str(error).splitlines()[0]
        return False, (
            ("Se creó la base pero no se pudieron crear las tablas.\n\n" if crear
             else "No se pudieron actualizar las tablas.\n\n")
            + f"{mensaje}"
        )
    return True, ""


def ruta_configuracion() -> Path:
    return carpeta_configuracion() / NOMBRE_ARCHIVO


def url_desde_campos(
    host: str,
    puerto: int | str,
    usuario: str,
    contrasena: str,
    base: str,
) -> str:
    """Build a SQLAlchemy URL from the fields the wizard shows.

    The password is percent-encoded because ``@``, ``:`` and ``/`` are legal in a
    password and would break the URL otherwise.
    """
    from urllib.parse import quote_plus

    usuario_codificado = quote_plus(usuario.strip())
    clave = quote_plus(contrasena)
    base_limpia = base.strip() or "taller"
    host_limpio = host.strip() or "localhost"
    return (
        f"postgresql+psycopg://{usuario_codificado}:{clave}"
        f"@{host_limpio}:{int(puerto)}/{base_limpia}"
    )


def campos_desde_url(url: str) -> dict[str, object]:
    """Split a saved URL back into the fields the form shows.

    Sirve para reabrir la configuración con los datos actuales en lugar de una
    pantalla en blanco que obliga a recordar la contraseña.
    """
    from sqlalchemy.engine import make_url

    try:
        analizada = make_url(url)
    except Exception:  # noqa: BLE001 - una URL inválida solo deja el formulario vacío
        return {}
    return {
        "host": analizada.host or "localhost",
        "puerto": analizada.port or 5432,
        "usuario": analizada.username or "",
        "contrasena": analizada.password or "",
        "base": analizada.database or "",
    }


@dataclass(frozen=True)
class ConfiguracionArranque:
    """What the wizard writes and the application reads on every start."""

    database_url: str = ""
    nombre: str = ""
    organizacion: str = ""
    descripcion: str = ""
    logo: Path | None = None
    #: Pedir usuario y contraseña al entrar. Se puede apagar; la autenticación y las
    #: cuentas siguen existiendo, y volver a encenderlo es una casilla.
    login_obligatorio: bool = True
    #: Cuenta con la que se entra cuando no se pide contraseña.
    usuario_por_defecto: str = ""

    @property
    def completa(self) -> bool:
        return bool(self.database_url and self.nombre)

    def como_diccionario(self) -> dict[str, Any]:
        return {
            "database_url": self.database_url,
            "branding": {
                "nombre": self.nombre,
                "organizacion": self.organizacion,
                "descripcion": self.descripcion,
                "logo": str(self.logo) if self.logo else "",
            },
            "acceso": {
                "login_obligatorio": self.login_obligatorio,
                "usuario_por_defecto": self.usuario_por_defecto,
            },
        }


#: Configuración leída una vez por proceso; el asistente la reemplaza al guardar.
_cache: ConfiguracionArranque | None = None


def cargar_configuracion(*, refrescar: bool = False) -> ConfiguracionArranque:
    """Read the startup configuration, or an empty one when there is none.

    A missing, empty or corrupt file is not an error: it means the application has
    not been configured yet, and the wizard will ask.
    """
    global _cache
    if _cache is not None and not refrescar:
        return _cache

    ruta = ruta_configuracion()
    if not ruta.is_file():
        _cache = ConfiguracionArranque()
        return _cache

    try:
        crudo = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _cache = ConfiguracionArranque()
        return _cache

    if not isinstance(crudo, dict):
        _cache = ConfiguracionArranque()
        return _cache

    marca = crudo.get("branding")
    marca = marca if isinstance(marca, dict) else {}
    logo = marca.get("logo")
    ruta_logo = Path(str(logo)) if isinstance(logo, str) and logo else None

    acceso = crudo.get("acceso")
    acceso = acceso if isinstance(acceso, dict) else {}
    # Sin la clave, se pide contraseña: el valor seguro es el que no deja entrar a
    # nadie sin identificarse, y apagarlo es una decisión explícita.
    login = acceso.get("login_obligatorio", True)

    _cache = ConfiguracionArranque(
        database_url=str(crudo.get("database_url") or ""),
        nombre=str(marca.get("nombre") or ""),
        organizacion=str(marca.get("organizacion") or ""),
        descripcion=str(marca.get("descripcion") or ""),
        logo=ruta_logo if ruta_logo and ruta_logo.is_file() else None,
        login_obligatorio=bool(login) if not isinstance(login, str) else _si_no(login),
        usuario_por_defecto=str(acceso.get("usuario_por_defecto") or ""),
    )
    return _cache


def _si_no(valor: str) -> bool:
    return valor.strip().lower() not in ("0", "no", "off", "false", "")


def ingreso_obligatorio() -> bool:
    """¿Hay que identificarse para entrar?

    ``TALLER_LOGIN=off`` lo apaga para una corrida sin tocar la configuración
    guardada: sirve para una demostración o para una máquina de consulta.
    """
    impuesto = os.environ.get("TALLER_LOGIN")
    if impuesto is not None:
        return _si_no(impuesto)
    return cargar_configuracion().login_obligatorio


def usuario_por_defecto() -> str:
    """La cuenta con la que se entra cuando no se pide contraseña."""
    impuesto = os.environ.get("TALLER_USUARIO_POR_DEFECTO")
    if impuesto and impuesto.strip():
        return impuesto.strip()
    return cargar_configuracion().usuario_por_defecto


def hay_configuracion_externa() -> bool:
    """True when the database is already configured outside the wizard.

    Un desarrollador con un ``.env`` no tiene que pasar por el asistente cada vez
    que abre el programa: si la conexión ya está definida, se usa.
    """
    if os.environ.get("TALLER_DATABASE_URL"):
        return True
    # Un archivo explícito evita que el ``.env`` del repositorio cuente cuando no
    # corresponde (los tests, o una instalación que vive en otra carpeta).
    impuesto = os.environ.get("TALLER_ENV_FILE")
    candidatos = (
        (Path(impuesto).expanduser(),)
        if impuesto
        else (Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env")
    )
    for candidato in candidatos:
        if not candidato.is_file():
            continue
        try:
            if "TALLER_DATABASE_URL" in candidato.read_text(encoding="utf-8"):
                return True
        except OSError:
            continue
    return False


def configuracion_completa() -> bool:
    return cargar_configuracion().completa


def copiar_logo(origen: Path) -> Path:
    """Copy the chosen logo into the configuration folder and return its path."""
    origen = Path(origen).expanduser()
    destino = carpeta_configuracion() / NOMBRE_LOGO
    if origen.resolve() != destino.resolve():
        shutil.copyfile(origen, destino)
    return destino


def guardar_configuracion(configuracion: ConfiguracionArranque) -> Path:
    """Write the configuration atomically enough for a desktop app."""
    global _cache
    ruta = ruta_configuracion()
    temporal = ruta.with_suffix(".json.tmp")
    temporal.write_text(
        json.dumps(configuracion.como_diccionario(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporal.replace(ruta)
    # El archivo guarda la contraseña de la base: solo el dueño debe poder leerlo.
    if os.name != "nt":
        os.chmod(ruta, 0o600)
    _cache = configuracion
    return ruta


def reiniciar_cache() -> None:
    """Forget the cached configuration. Used by tests and after saving."""
    global _cache
    _cache = None
