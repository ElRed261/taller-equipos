"""Text normalisation shared by the ETL, the DTOs and the search proxy.

It lives here, not inside the ETL, because the search proxy and the alias
resolver must agree on exactly what "the same text" means. Two copies of this
logic would drift and the grid would stop finding rows the importer merged.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

_ESPACIOS: Final = re.compile(r"\s+")


def normalizar_espacios(valor: str | None) -> str | None:
    """Trim, collapse whitespace (including non-breaking spaces) and drop empties."""
    if valor is None:
        return None
    limpio = _ESPACIOS.sub(" ", valor.replace("\xa0", " ")).strip()
    return limpio or None


def clave_alias(valor: str) -> str:
    """Accent-, case- and whitespace-insensitive key used to compare texts.

    ``Agrometeorología``, ``Agrometeorologia`` and ``agrometeorologia`` collapse
    to the same key; so does what the user types in the search box.
    """
    descompuesto = unicodedata.normalize("NFKD", valor.replace("\xa0", " "))
    sin_tildes = "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")
    return _ESPACIOS.sub(" ", sin_tildes).strip().lower()
