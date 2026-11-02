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

import json
import os
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


@dataclass(frozen=True)
class ConfiguracionArranque:
    """What the wizard writes and the application reads on every start."""

    database_url: str = ""
    nombre: str = ""
    organizacion: str = ""
    descripcion: str = ""
    logo: Path | None = None

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

    _cache = ConfiguracionArranque(
        database_url=str(crudo.get("database_url") or ""),
        nombre=str(marca.get("nombre") or ""),
        organizacion=str(marca.get("organizacion") or ""),
        descripcion=str(marca.get("descripcion") or ""),
        logo=ruta_logo if ruta_logo and ruta_logo.is_file() else None,
    )
    return _cache


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
    _cache = configuracion
    return ruta


def reiniciar_cache() -> None:
    """Forget the cached configuration. Used by tests and after saving."""
    global _cache
    _cache = None
