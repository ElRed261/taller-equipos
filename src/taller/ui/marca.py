"""Brand customisation: the name, the logo and the one-line description.

The repository ships a generic product. An organisation makes it its own with a
``branding.json`` file at the project root, which is not committed: the logo and
the name belong to whoever deploys it, not to the code base.

Resolution order, first match wins:

1. ``TALLER_BRANDING`` environment variable pointing at a JSON file.
2. ``branding.json`` at the project root.
3. What the first-run wizard saved in the user's configuration folder.
4. The generic defaults: neutral mark, generic name.

Everything the application shows about itself comes from here, so a fork does not
have to hunt strings through the widgets.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

NOMBRE_GENERICO: Final = "Taller de equipos"
DESCRIPCION_GENERICA: Final = "Registro y control de equipos de soporte técnico"
ORGANIZACION_GENERICA: Final = "Taller de equipos"

#: The neutral mark that ships with the repository.
LOGO_GENERICO: Final = Path(__file__).parent / "assets" / "logo.png"

#: Project root: ``src/taller/ui/marca.py`` -> up three levels.
RAIZ_PROYECTO: Final = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Marca:
    """What the application calls itself and which mark it shows."""

    nombre: str = NOMBRE_GENERICO
    organizacion: str = ORGANIZACION_GENERICA
    descripcion: str = DESCRIPCION_GENERICA
    logo: Path = LOGO_GENERICO

    @property
    def titulo_ventana(self) -> str:
        return self.nombre


def _ruta_configuracion(ruta: Path | None = None) -> Path | None:
    if ruta is not None:
        return ruta
    desde_entorno = os.environ.get("TALLER_BRANDING")
    if desde_entorno:
        return Path(desde_entorno).expanduser()
    candidata = RAIZ_PROYECTO / "branding.json"
    return candidata if candidata.is_file() else None


def _marca_del_asistente() -> Marca:
    """Identity saved by the first-run wizard, if there is one."""
    from taller.arranque import cargar_configuracion

    guardada = cargar_configuracion()
    if not guardada.nombre:
        return Marca()
    return Marca(
        nombre=guardada.nombre,
        organizacion=guardada.organizacion or guardada.nombre,
        descripcion=guardada.descripcion or DESCRIPCION_GENERICA,
        logo=guardada.logo or LOGO_GENERICO,
    )


def cargar_marca(ruta: Path | None = None) -> Marca:
    """Read the brand configuration, or return the generic defaults.

    A broken or partial file never crashes the application: unknown keys are
    ignored, a missing logo falls back to the neutral one, and an unreadable file
    falls back to the generic brand.
    """
    archivo = _ruta_configuracion(ruta)
    if archivo is None or not Path(archivo).is_file():
        return _marca_del_asistente()

    try:
        crudo: dict[str, Any] = json.loads(Path(archivo).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Marca()

    if not isinstance(crudo, dict):
        return Marca()

    logo = LOGO_GENERICO
    ruta_logo = crudo.get("logo")
    if isinstance(ruta_logo, str) and ruta_logo.strip():
        candidata = Path(ruta_logo).expanduser()
        if not candidata.is_absolute():
            candidata = Path(archivo).parent / candidata
        if candidata.is_file():
            logo = candidata

    def _texto(clave: str, por_defecto: str) -> str:
        valor = crudo.get(clave)
        return valor.strip() if isinstance(valor, str) and valor.strip() else por_defecto

    return Marca(
        nombre=_texto("nombre", NOMBRE_GENERICO),
        organizacion=_texto("organizacion", ORGANIZACION_GENERICA),
        descripcion=_texto("descripcion", DESCRIPCION_GENERICA),
        logo=logo,
    )
