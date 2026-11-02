"""DTO de usuario: lo mínimo para la pantalla, sin nada del hash."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict


class UsuarioLeido(BaseModel):
    """Un usuario tal como se muestra. Nunca incluye el hash ni la contraseña."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    activo: bool = True
    es_admin: bool = False
    ultimo_acceso: dt.datetime | None = None
