"""Shared fixtures.

The integration fixture opens a real transaction against the development
database and rolls it back afterwards, so a test never leaves a row behind and
the 568 imported movements stay untouched.

The Qt platform is forced to ``offscreen`` before Qt is imported: the UI tests
must run on a machine without a display and without opening windows.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from collections.abc import Iterator  # noqa: E402

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, sessionmaker

from taller.database.connection import get_engine


def _base_disponible() -> bool:
    try:
        with get_engine().connect() as conexion:
            conexion.execute(text("select 1"))
    except Exception:  # pragma: no cover - depends on the machine
        return False
    return True


@pytest.fixture
def conexion() -> Iterator[Connection]:
    if not _base_disponible():
        pytest.skip("development PostgreSQL is not reachable (start it with pg_ctl)")
    motor = get_engine()
    conexion = motor.connect()
    transaccion = conexion.begin()
    try:
        yield conexion
    finally:
        transaccion.rollback()
        conexion.close()


@pytest.fixture
def session(conexion: Connection) -> Iterator[Session]:
    fabrica = sessionmaker(bind=conexion, expire_on_commit=False)
    sesion = fabrica()
    try:
        yield sesion
    finally:
        sesion.close()
