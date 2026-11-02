"""Application services: the seam between widgets and the database.

Every method opens its own ``session_scope()`` and returns DTOs. That is the
rule from S11 (a session per unit of work, never shared) applied in the place
where the UI cannot break it: a widget never sees a ``Session``, so a widget can
never keep one alive across threads or forget to close it.

The class satisfies the ``PersistenciaMovimientos`` protocol the table model
expects, so the model can be handed a service directly.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import select

from taller.database.connection import session_scope
from taller.database.models import Area, Movimiento, Tecnico, TipoEquipo
from taller.database.repositories import (
    CatalogoRepository,
    MovimientoRepository,
    UsuarioRepository,
)
from taller.schemas.movimiento import (
    CatalogoConUso,
    CatalogoLeido,
    Estado,
    MovimientoActualizar,
    MovimientoCrear,
    MovimientoLeido,
    ResumenEstados,
)
from taller.schemas.usuario import UsuarioLeido

CATALOGOS: dict[str, type[Area] | type[Tecnico] | type[TipoEquipo]] = {
    "area": Area,
    "tecnico": Tecnico,
    "tipo_equipo": TipoEquipo,
}


class ServicioTaller:
    """One instance per running application, bound to the logged-in user."""

    def __init__(self, usuario: str, *, es_admin: bool = False) -> None:
        if not usuario.strip():
            raise ValueError("hace falta un usuario para atribuir los cambios")
        self.usuario = usuario.strip()
        self.es_admin = es_admin

    # -------------------------------------------------------------- lecturas

    def listar_movimientos(
        self,
        *,
        estado: Estado | None = None,
        area_id: int | None = None,
        solo_pendientes_revision: bool = False,
        limite: int | None = None,
    ) -> list[MovimientoLeido]:
        with session_scope() as sesion:
            return MovimientoRepository(sesion).listar(
                estado=estado,
                area_id=area_id,
                solo_pendientes_revision=solo_pendientes_revision,
                limite=limite,
            )

    def obtener(self, movimiento_id: int) -> MovimientoLeido:
        with session_scope() as sesion:
            return MovimientoRepository(sesion).obtener(movimiento_id)

    def resumen(self) -> ResumenEstados:
        with session_scope() as sesion:
            return MovimientoRepository(sesion).resumen()

    def historial(self, movimiento_id: int) -> list[dict[str, Any]]:
        with session_scope() as sesion:
            return MovimientoRepository(sesion).historial(movimiento_id)

    def modelos_sugeridos(self, limite: int = 60) -> list[str]:
        with session_scope() as sesion:
            return MovimientoRepository(sesion).modelos_sugeridos(limite)

    # -------------------------------------------------------------- escrituras

    def crear_movimiento(self, datos: MovimientoCrear) -> MovimientoLeido:
        with session_scope() as sesion:
            return MovimientoRepository(sesion).crear(datos, usuario=self.usuario)

    def actualizar(
        self,
        movimiento_id: int,
        cambios: MovimientoActualizar,
        *,
        usuario: str | None = None,
    ) -> MovimientoLeido:
        with session_scope() as sesion:
            return MovimientoRepository(sesion).actualizar(
                movimiento_id, cambios, usuario=usuario or self.usuario
            )

    def marcar_salida(
        self, movimiento_id: int, fecha: dt.date | None = None
    ) -> MovimientoLeido:
        """The one-action flow: dispatching an equipment unit."""
        return self.actualizar(
            movimiento_id, MovimientoActualizar(fecha_salida=fecha or dt.date.today())
        )

    def eliminar_movimiento(self, movimiento_id: int) -> None:
        """Delete a record for good. Only the administration panel calls this."""
        with session_scope() as sesion:
            MovimientoRepository(sesion).eliminar(movimiento_id, usuario=self.usuario)

    def marcar_revisado(self, movimiento_id: int) -> MovimientoLeido:
        with session_scope() as sesion:
            return MovimientoRepository(sesion).marcar_revisado(
                movimiento_id, usuario=self.usuario
            )

    # ---------------------------------------------------------------- catálogos

    def areas(self, *, solo_activos: bool = True) -> list[CatalogoLeido]:
        return self._catalogo("area", solo_activos=solo_activos)

    def tecnicos(self, *, solo_activos: bool = True) -> list[CatalogoLeido]:
        return self._catalogo("tecnico", solo_activos=solo_activos)

    def tipos_equipo(self, *, solo_activos: bool = True) -> list[CatalogoLeido]:
        return self._catalogo("tipo_equipo", solo_activos=solo_activos)

    def catalogo_con_uso(
        self, dimension: str, *, solo_activos: bool = False
    ) -> list[CatalogoConUso]:
        """Every row of one catalog with how many movements depend on it."""
        with session_scope() as sesion:
            filas = CatalogoRepository(sesion).listar_con_uso(
                CATALOGOS[dimension], solo_activos=solo_activos
            )
        return [
            CatalogoConUso(id=fila.id, nombre=fila.nombre, activo=fila.activo, movimientos=total)
            for fila, total in filas
        ]

    def renombrar_catalogo(self, dimension: str, catalogo_id: int, nombre: str) -> CatalogoLeido:
        with session_scope() as sesion:
            return CatalogoRepository(sesion).renombrar(
                CATALOGOS[dimension], catalogo_id, nombre, usuario=self.usuario
            )

    def desactivar_catalogo(self, dimension: str, catalogo_id: int) -> None:
        with session_scope() as sesion:
            CatalogoRepository(sesion).desactivar(
                CATALOGOS[dimension], catalogo_id, usuario=self.usuario
            )

    def activar_catalogo(self, dimension: str, catalogo_id: int) -> None:
        with session_scope() as sesion:
            CatalogoRepository(sesion).activar(
                CATALOGOS[dimension], catalogo_id, usuario=self.usuario
            )

    def fusionar_catalogo(self, dimension: str, origen_id: int, destino_id: int) -> int:
        """Repoint every reference and deactivate the absorbed row."""
        with session_scope() as sesion:
            return CatalogoRepository(sesion).fusionar(
                CATALOGOS[dimension], origen_id, destino_id, usuario=self.usuario
            )

    def crear_catalogo(self, dimension: str, nombre: str) -> CatalogoLeido:
        with session_scope() as sesion:
            return CatalogoRepository(sesion).crear(
                CATALOGOS[dimension], nombre, usuario=self.usuario
            )

    def _catalogo(self, dimension: str, *, solo_activos: bool) -> list[CatalogoLeido]:
        with session_scope() as sesion:
            return CatalogoRepository(sesion).listar(
                CATALOGOS[dimension], solo_activos=solo_activos
            )

    # --------------------------------------------------------------- usuarios

    @staticmethod
    def autenticar(nombre: str, clave: str) -> UsuarioLeido | None:
        """La cuenta que corresponde a esas credenciales, o ``None``."""
        with session_scope() as sesion:
            return UsuarioRepository(sesion).autenticar(nombre, clave)

    @staticmethod
    def hay_administrador() -> bool:
        with session_scope() as sesion:
            return UsuarioRepository(sesion).hay_administrador()

    @staticmethod
    def cuentas_existentes() -> list[UsuarioLeido]:
        """Todas las cuentas, para ofrecer los nombres que ya están en uso."""
        with session_scope() as sesion:
            return UsuarioRepository(sesion).listar()

    @staticmethod
    def crear_administrador(nombre: str, clave: str) -> UsuarioLeido:
        """Crea la primera cuenta administradora, o le pone clave a una existente."""
        with session_scope() as sesion:
            repositorio = UsuarioRepository(sesion)
            existente = [
                u
                for u in repositorio.listar()
                if u.nombre.lower() == nombre.strip().lower()
            ]
            if existente:
                return repositorio.fijar_clave_de_existente(nombre, clave, es_admin=True)
            return repositorio.crear(nombre, clave, es_admin=True)

    def listar_usuarios(self) -> list[UsuarioLeido]:
        with session_scope() as sesion:
            return UsuarioRepository(sesion).listar()

    def crear_usuario(
        self, nombre: str, clave: str, *, es_admin: bool = False
    ) -> UsuarioLeido:
        with session_scope() as sesion:
            return UsuarioRepository(sesion).crear(nombre, clave, es_admin=es_admin)

    def cambiar_clave_usuario(self, usuario_id: int, clave: str) -> None:
        with session_scope() as sesion:
            UsuarioRepository(sesion).cambiar_clave(usuario_id, clave)

    def alternar_usuario(self, usuario_id: int) -> UsuarioLeido:
        with session_scope() as sesion:
            return UsuarioRepository(sesion).alternar_activo(usuario_id)

    def asignar_administrador(self, usuario_id: int, *, es_admin: bool) -> UsuarioLeido:
        with session_scope() as sesion:
            return UsuarioRepository(sesion).hacer_administrador(
                usuario_id, es_admin=es_admin
            )

    # ------------------------------------------------------------------ salud

    def conexion_ok(self) -> tuple[bool, str]:
        """Cheap connectivity check for the status bar and the startup guard."""
        try:
            with session_scope() as sesion:
                sesion.execute(select(Movimiento.id).limit(1))
        except Exception as exc:  # pragma: no cover - depends on the network
            return False, str(exc).splitlines()[0][:160]
        return True, "conectado"
