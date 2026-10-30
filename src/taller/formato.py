"""Display and interchange formats.

The business dates of this system are calendar days, never instants: the legacy
source stored every one of its 1136 dates as ``12:00:00 a. m.``, so the time
component carries no information. The user requirement is explicit: show and
export ``dd/mm/aaaa``, no hours.

Those two facts are the same requirement seen twice, so they live here: the
database stores ``DATE`` (see the schema), and this module is the only place
that decides how a day is written for a human.
"""

from __future__ import annotations

import datetime as dt
from typing import Final

#: The one accepted display and export format.
FORMATO_FECHA: Final = "%d/%m/%Y"


def formatear_fecha(valor: dt.date | dt.datetime | None) -> str:
    """Write a business date as ``dd/mm/aaaa``.

    ``None`` becomes an empty string: the source has genuinely empty dates and
    the grid must show nothing rather than a placeholder that looks like data.
    A ``datetime`` is accepted for convenience but its time is discarded — dates
    with hours are exactly what this project removes.
    """
    if valor is None:
        return ""
    if isinstance(valor, dt.datetime):
        valor = valor.date()
    return valor.strftime(FORMATO_FECHA)


def parsear_fecha_usuario(texto: str) -> dt.date:
    """Parse what a technician types as ``dd/mm/aaaa``.

    Zero padding is optional (``7/2/2024`` is accepted), hours are not, and the
    error message names the expected format so the form can show it verbatim.
    """
    limpio = texto.strip()
    if not limpio:
        raise ValueError("fecha vacía: se esperaba dd/mm/aaaa")
    try:
        return dt.datetime.strptime(limpio, FORMATO_FECHA).date()
    except ValueError as exc:
        raise ValueError(f"fecha inválida: {texto!r} (formato esperado dd/mm/aaaa)") from exc
