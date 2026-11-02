"""Repository behaviour against the real development database.

Every test runs inside a transaction that is rolled back, so the 568 imported
movements and the catalogs are never modified by the suite.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from taller.database.models import Area, Movimiento, MovimientoTecnico, Tecnico
from taller.database.repositories import (
    CatalogoNoEncontrado,
    CatalogoRepository,
    MovimientoNoEncontrado,
    MovimientoRepository,
    NombreDuplicado,
)
from taller.schemas.movimiento import (
    FechasInvalidas,
    MovimientoActualizar,
    MovimientoCrear,
)

TOTAL_IMPORTADO = 568



#: Quien firma los cambios en las pruebas de catálogo.
OPERADOR = "prueba-operador"

class TestLectura:
    def test_lists_every_imported_movement(self, session: Session) -> None:
        assert len(MovimientoRepository(session).listar()) == TOTAL_IMPORTADO

    def test_newest_intake_first_and_empty_dates_last(self, session: Session) -> None:
        filas = MovimientoRepository(session).listar()
        fechas = [f.fecha_entrada for f in filas if f.fecha_entrada is not None]
        assert fechas == sorted(fechas, reverse=True)
        assert filas[-1].fecha_entrada is None

    def test_the_derived_state_comes_from_the_view(self, session: Session) -> None:
        filas = MovimientoRepository(session).listar()
        for fila in filas:
            esperado = (
                "despachado"
                if fila.fecha_salida is not None
                else "en_taller"
                if fila.fecha_entrada is not None
                else "sin_datos"
            )
            assert fila.estado == esperado

    def test_filter_by_state(self, session: Session) -> None:
        repo = MovimientoRepository(session)
        assert len(repo.listar(estado="en_taller")) == 135
        assert len(repo.listar(estado="despachado")) == 431
        assert len(repo.listar(estado="sin_datos")) == 2

    def test_catalog_names_come_resolved_from_one_query(self, session: Session) -> None:
        fila = MovimientoRepository(session).listar(limite=1)[0]
        assert fila.area is not None
        assert fila.soporte

    def test_summary_matches_the_database(self, session: Session) -> None:
        # Se compara contra la base y no contra números fijos: el estado de los
        # datos cambia con cada migración y con el uso de la aplicación.
        resumen = MovimientoRepository(session).resumen()
        assert resumen.total == TOTAL_IMPORTADO
        assert resumen.en_taller + resumen.despachado + resumen.sin_datos == TOTAL_IMPORTADO
        pendientes = session.scalar(
            select(func.count())
            .select_from(Movimiento)
            .where(Movimiento.requiere_revision.is_(True))
        )
        assert resumen.pendientes_revision == pendientes

    def test_missing_movement_raises(self, session: Session) -> None:
        with pytest.raises(MovimientoNoEncontrado):
            MovimientoRepository(session).obtener(10**9)


class TestCreacion:
    def test_creates_a_movement_that_is_still_in_the_workshop(self, session: Session) -> None:
        repo = MovimientoRepository(session)
        creado = repo.crear(
            MovimientoCrear(
                fecha_entrada=dt.date(2026, 10, 30),
                modelo="Dell Optiplex 3050",
                diagnostico="no enciende",
            ),
            usuario="operador",
        )
        assert creado.estado == "en_taller"
        assert creado.fecha_entrada_texto == "30/10/2026"

    def test_a_movement_without_dates_is_sin_datos(self, session: Session) -> None:
        creado = MovimientoRepository(session).crear(
            MovimientoCrear(nota="solo nota"), usuario="operador"
        )
        assert creado.estado == "sin_datos"

    def test_the_app_never_creates_flagged_rows(self, session: Session) -> None:
        creado = MovimientoRepository(session).crear(MovimientoCrear(nota="x"), usuario="operador")
        assert creado.requiere_revision is False
        origen = session.scalar(select(Movimiento.origen).where(Movimiento.id == creado.id))
        assert origen == "app"

    def test_technicians_are_linked_with_a_principal(self, session: Session) -> None:
        tecnicos = list(session.scalars(select(Tecnico.id).order_by(Tecnico.id).limit(2)))
        creado = MovimientoRepository(session).crear(
            MovimientoCrear(nota="x", tecnicos=tecnicos), usuario="operador"
        )
        assert len(creado.soporte) == 2

    def test_an_inverted_creation_is_rejected_before_it_reaches_the_database(
        self, session: Session
    ) -> None:
        with pytest.raises(FechasInvalidas):
            MovimientoRepository(session).crear(
                MovimientoCrear(
                    fecha_entrada=dt.date(2026, 10, 30),
                    fecha_salida=dt.date(2026, 10, 1),
                ),
                usuario="operador",
            )


class TestEdicion:
    def _uno(self, session: Session) -> int:
        return MovimientoRepository(session).listar(limite=1)[0].id

    def test_a_change_is_applied_and_audited(self, session: Session) -> None:
        repo = MovimientoRepository(session)
        movimiento_id = self._uno(session)
        repo.actualizar(
            movimiento_id, MovimientoActualizar(nota="nota nueva"), usuario="operador"
        )
        assert repo.obtener(movimiento_id).nota == "nota nueva"

        historial = repo.historial(movimiento_id)
        assert historial[0]["campo"] == "nota"
        assert historial[0]["valor_nuevo"] == "nota nueva"
        assert historial[0]["usuario"] == "operador"

    def test_an_unchanged_field_writes_no_audit_row(self, session: Session) -> None:
        # Se compara la cantidad y no «historial vacío»: el registro puede traer
        # entradas de una migración anterior, y eso no es culpa de este test.
        repo = MovimientoRepository(session)
        movimiento_id = self._uno(session)
        antes = len(repo.historial(movimiento_id))
        actual = repo.obtener(movimiento_id).nota
        repo.actualizar(movimiento_id, MovimientoActualizar(nota=actual), usuario="operador")
        assert len(repo.historial(movimiento_id)) == antes

    def test_clearing_a_field_is_an_explicit_change(self, session: Session) -> None:
        repo = MovimientoRepository(session)
        movimiento_id = self._uno(session)
        repo.actualizar(movimiento_id, MovimientoActualizar(nota="algo"), usuario="operador")
        repo.actualizar(movimiento_id, MovimientoActualizar(nota=None), usuario="operador")
        assert repo.obtener(movimiento_id).nota is None

    def test_setting_the_departure_date_flips_the_state(self, session: Session) -> None:
        repo = MovimientoRepository(session)
        despachado = repo.listar(estado="despachado", limite=1)[0]
        assert despachado.fecha_salida is not None

        repo.actualizar(
            despachado.id, MovimientoActualizar(fecha_salida=None), usuario="operador"
        )
        assert repo.obtener(despachado.id).estado == "en_taller"

    def test_a_partial_edit_is_validated_against_the_stored_intake_date(
        self, session: Session
    ) -> None:
        repo = MovimientoRepository(session)
        movimiento_id = self._uno(session)
        antes = repo.obtener(movimiento_id)
        assert antes.fecha_entrada is not None
        with pytest.raises(FechasInvalidas):
            repo.actualizar(
                movimiento_id,
                MovimientoActualizar(fecha_salida=antes.fecha_entrada - dt.timedelta(days=3)),
                usuario="operador",
            )
        assert repo.obtener(movimiento_id) == antes

    def test_technicians_are_replaced_not_appended(self, session: Session) -> None:
        repo = MovimientoRepository(session)
        movimiento_id = self._uno(session)
        tecnicos = list(session.scalars(select(Tecnico.id).order_by(Tecnico.id).limit(1)))
        repo.actualizar(movimiento_id, MovimientoActualizar(tecnicos=tecnicos), usuario="operador")
        assert len(repo.obtener(movimiento_id).soporte) == 1


class TestRevision:
    def _invertida(self, session: Session) -> int:
        """Crea una fila marcada con fechas invertidas.

        No se toma de los datos importados: después de repararlos no queda ninguna,
        y una prueba que depende de que exista un dato roto deja de probar nada en
        cuanto el dato se arregla.
        """
        movimiento = Movimiento(
            origen="csv_v1",
            legacy_linea=990001,
            fecha_entrada=dt.date(2024, 5, 1),
            fecha_salida=dt.date(2024, 4, 1),
            requiere_revision=True,
        )
        session.add(movimiento)
        session.flush()
        return movimiento.id

    def test_a_flagged_row_cannot_be_cleared_while_the_dates_are_inverted(
        self, session: Session
    ) -> None:
        repo = MovimientoRepository(session)
        movimiento_id = self._invertida(session)
        with pytest.raises(FechasInvalidas):
            repo.marcar_revisado(movimiento_id, usuario="operador")
        assert repo.obtener(movimiento_id).requiere_revision is True

    def test_fixing_the_dates_then_clearing_the_flag_works(self, session: Session) -> None:
        repo = MovimientoRepository(session)
        movimiento_id = self._invertida(session)
        fila = repo.obtener(movimiento_id)
        assert fila.fecha_entrada is not None

        repo.actualizar(
            movimiento_id,
            MovimientoActualizar(fecha_salida=fila.fecha_entrada),
            usuario="operador",
        )
        assert repo.obtener(movimiento_id).requiere_revision is True, "arreglar no limpia la marca"

        revisado = repo.marcar_revisado(movimiento_id, usuario="operador")
        assert revisado.requiere_revision is False
        historial = repo.historial(movimiento_id)
        assert any(entrada["campo"] == "requiere_revision" for entrada in historial)

    def test_a_flagged_row_without_dates_cannot_be_marked_reviewed(
        self, session: Session
    ) -> None:
        # Regresión del incidente del 30/10/2026: tres filas sin fechas quedaron
        # liberadas porque la validación de orden no tenía nada que comparar.
        movimiento_id = session.scalar(
            select(Movimiento.id)
            .where(
                Movimiento.requiere_revision.is_(True),
                Movimiento.fecha_entrada.is_(None),
            )
            .limit(1)
        )
        assert movimiento_id is not None
        repo = MovimientoRepository(session)
        with pytest.raises(FechasInvalidas, match="sin fecha de entrada"):
            repo.marcar_revisado(int(movimiento_id), usuario="operador")
        assert repo.obtener(int(movimiento_id)).requiere_revision is True

    def test_clearing_an_already_clean_row_is_a_no_op(self, session: Session) -> None:
        repo = MovimientoRepository(session)
        movimiento_id = repo.listar(limite=1)[0].id
        assert repo.marcar_revisado(movimiento_id, usuario="operador").requiere_revision is False


class TestCatalogos:
    def test_creating_and_renaming(self, session: Session) -> None:
        repo = CatalogoRepository(session)
        creada = repo.crear(Area, "  Taller Nuevo  ", usuario=OPERADOR)
        assert creada.nombre == "Taller Nuevo"
        renombrada = repo.renombrar(
            Area, creada.id, "Taller Renombrado", usuario=OPERADOR
        )
        assert renombrada.nombre == "Taller Renombrado"

    def test_duplicate_names_are_rejected(self, session: Session) -> None:
        repo = CatalogoRepository(session)
        with pytest.raises(NombreDuplicado):
            repo.crear(Area, "Contabilidad", usuario=OPERADOR)

    def test_renaming_onto_an_existing_name_is_rejected(self, session: Session) -> None:
        repo = CatalogoRepository(session)
        areas = repo.listar(Area)
        with pytest.raises(NombreDuplicado):
            repo.renombrar(Area, areas[0].id, areas[1].nombre, usuario=OPERADOR)

    def test_deactivation_keeps_history_intact(self, session: Session) -> None:
        repo = CatalogoRepository(session)
        area = next(a for a in repo.listar(Area) if a.nombre == "Contabilidad")
        antes = session.scalar(
            select(func.count()).select_from(Movimiento).where(Movimiento.area_id == area.id)
        )
        repo.desactivar(Area, area.id, usuario=OPERADOR)
        despues = session.scalar(
            select(func.count()).select_from(Movimiento).where(Movimiento.area_id == area.id)
        )
        assert antes == despues
        assert area.id not in [a.id for a in repo.listar(Area)]

    def test_missing_catalog_row_raises(self, session: Session) -> None:
        with pytest.raises(CatalogoNoEncontrado):
            CatalogoRepository(session).desactivar(Area, 10**9, usuario=OPERADOR)

    def test_merging_areas_repoints_movements_and_deactivates_the_source(
        self, session: Session
    ) -> None:
        repo = CatalogoRepository(session)
        areas = repo.listar(Area)
        origen, destino = areas[0], areas[1]
        movidos = session.scalar(
            select(func.count()).select_from(Movimiento).where(Movimiento.area_id == origen.id)
        )
        assert movidos

        assert repo.fusionar(Area, origen.id, destino.id, usuario=OPERADOR) == movidos

        restantes = session.scalar(
            select(func.count()).select_from(Movimiento).where(Movimiento.area_id == origen.id)
        )
        assert restantes == 0
        assert session.get(Area, origen.id).activo is False
        assert origen.id not in [a.id for a in repo.listar(Area)]

    def test_merging_technicians_repoints_every_link(self, session: Session) -> None:
        repo = CatalogoRepository(session)
        tecnicos = repo.listar(Tecnico)
        origen, destino = tecnicos[0], tecnicos[1]

        repo.fusionar(Tecnico, origen.id, destino.id, usuario=OPERADOR)

        quedan = session.scalar(
            select(func.count())
            .select_from(MovimientoTecnico)
            .where(MovimientoTecnico.tecnico_id == origen.id)
        )
        assert quedan == 0

        # A movement that already had both technicians keeps exactly one link:
        # the merge deletes the duplicate instead of violating the primary key.
        maximo = session.scalar(
            select(func.count())
            .select_from(MovimientoTecnico)
            .where(MovimientoTecnico.tecnico_id == destino.id)
            .group_by(MovimientoTecnico.movimiento_id)
            .order_by(func.count().desc())
            .limit(1)
        )
        assert maximo == 1

    def test_merging_a_row_with_itself_is_refused(self, session: Session) -> None:
        repo = CatalogoRepository(session)
        area = repo.listar(Area)[0]
        with pytest.raises(ValueError, match="consigo mismo"):
            repo.fusionar(Area, area.id, area.id, usuario=OPERADOR)


class TestCatalogosCompartidos:
    """Los catálogos viven en la base, no en cada puesto.

    Este test es el que respalda la afirmación: lo que agrega un usuario desde su
    máquina lo ve cualquier otro, porque no hay nada guardado localmente.
    """

    def test_un_area_creada_desde_un_puesto_la_ve_otro(self) -> None:
        from taller.database.connection import session_scope
        from taller.servicios import ServicioTaller

        nombre = "__area_compartida_de_prueba__"
        try:
            creada = ServicioTaller("puesto-uno").crear_catalogo("area", nombre)
            assert creada.id > 0

            # Segundo servicio: abre su propia sesión y su propia conexión.
            areas_del_otro = [a.nombre for a in ServicioTaller("puesto-dos").areas()]
            assert nombre in areas_del_otro
        finally:
            with session_scope() as sesion:
                fila = sesion.scalar(select(Area).where(Area.nombre == nombre))
                if fila is not None:
                    sesion.delete(fila)


class TestBorrado:
    """Eliminar un registro deja constancia y no deja huérfanos."""

    def _uno_con_vinculos(self, session: Session) -> int:
        movimiento_id = session.scalar(
            select(Movimiento.id)
            .join(MovimientoTecnico, MovimientoTecnico.movimiento_id == Movimiento.id)
            .limit(1)
        )
        assert movimiento_id is not None
        return int(movimiento_id)

    def test_elimina_el_registro_sus_vinculos_y_su_auditoria(
        self, session: Session
    ) -> None:
        from sqlalchemy import func

        from taller.database.models import AuditoriaEdicion, MovimientoEliminado

        movimiento_id = self._uno_con_vinculos(session)
        repo = MovimientoRepository(session)
        codigo = repo.obtener(movimiento_id).codigo_inventario

        repo.eliminar(movimiento_id, usuario="admin")

        assert session.get(Movimiento, movimiento_id) is None
        assert (
            session.scalar(
                select(func.count())
                .select_from(MovimientoTecnico)
                .where(MovimientoTecnico.movimiento_id == movimiento_id)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditoriaEdicion)
                .where(AuditoriaEdicion.movimiento_id == movimiento_id)
            )
            == 0
        )

        snapshot = session.scalar(
            select(MovimientoEliminado).where(
                MovimientoEliminado.movimiento_id == movimiento_id
            )
        )
        assert snapshot is not None, "no quedó constancia del borrado"
        assert snapshot.usuario_etiqueta == "admin"
        assert codigo is None or codigo in snapshot.snapshot

    def test_el_snapshot_conserva_los_datos_del_registro(self, session: Session) -> None:
        from taller.database.models import MovimientoEliminado

        movimiento_id = self._uno_con_vinculos(session)
        repo = MovimientoRepository(session)
        antes = repo.obtener(movimiento_id)

        repo.eliminar(movimiento_id, usuario="admin")

        snapshot = session.scalar(
            select(MovimientoEliminado).where(
                MovimientoEliminado.movimiento_id == movimiento_id
            )
        )
        assert snapshot is not None
        if antes.modelo:
            assert antes.modelo in snapshot.snapshot
        if antes.area:
            assert antes.area in snapshot.snapshot

    def test_eliminar_dos_veces_falla_la_segunda(self, session: Session) -> None:
        movimiento_id = self._uno_con_vinculos(session)
        repo = MovimientoRepository(session)
        repo.eliminar(movimiento_id, usuario="admin")
        with pytest.raises(MovimientoNoEncontrado):
            repo.eliminar(movimiento_id, usuario="admin")


class TestMismoDia:
    """Un equipo puede entrar y salir el mismo día: es el caso más común."""

    def test_crear_un_movimiento_que_entra_y_sale_el_mismo_dia(self, session: Session) -> None:
        repo = MovimientoRepository(session)
        hoy = dt.date(2026, 10, 30)
        creado = repo.crear(
            MovimientoCrear(fecha_entrada=hoy, fecha_salida=hoy, nota="exprés"),
            usuario="operador",
        )
        assert creado.fecha_entrada == creado.fecha_salida == hoy
        assert creado.estado == "despachado"

    def test_editar_la_salida_al_mismo_dia_de_la_entrada(self, session: Session) -> None:
        repo = MovimientoRepository(session)
        movimiento_id = repo.listar(limite=1)[0].id
        fila = repo.obtener(movimiento_id)
        assert fila.fecha_entrada is not None
        actualizada = repo.actualizar(
            movimiento_id,
            MovimientoActualizar(fecha_salida=fila.fecha_entrada),
            usuario="operador",
        )
        assert actualizada.fecha_salida == actualizada.fecha_entrada
        assert actualizada.estado == "despachado"

    def test_la_base_no_tiene_ninguna_fecha_invertida(self, session: Session) -> None:
        invertidas = session.scalar(
            select(func.count())
            .select_from(Movimiento)
            .where(
                Movimiento.fecha_entrada.is_not(None),
                Movimiento.fecha_salida.is_not(None),
                Movimiento.fecha_salida < Movimiento.fecha_entrada,
            )
        )
        assert invertidas == 0


class TestAuditoriaDeCatalogo:
    """Renombrar un área también es un cambio que alguien hizo."""

    def test_crear_deja_el_rastro(self, session) -> None:  # noqa: ANN001
        repo = CatalogoRepository(session)
        creada = repo.crear(Area, "Prueba Auditoria", usuario="prueba-quien")

        filas = [f for f in repo.historial() if f["registro_id"] == creada.id]
        assert filas, "no quedó ninguna fila de auditoría"
        assert filas[0]["accion"] == "crear"
        assert filas[0]["valor_nuevo"] == "Prueba Auditoria"
        assert filas[0]["usuario"] == "prueba-quien"
        assert filas[0]["catalogo"] == "area"

    def test_renombrar_guarda_el_nombre_anterior_y_el_nuevo(self, session) -> None:  # noqa: ANN001
        repo = CatalogoRepository(session)
        creada = repo.crear(Area, "Prueba Antes", usuario="prueba-quien")
        repo.renombrar(Area, creada.id, "Prueba Despues", usuario="prueba-quien")

        filas = [
            f
            for f in repo.historial()
            if f["registro_id"] == creada.id and f["accion"] == "renombrar"
        ]
        assert len(filas) == 1
        assert filas[0]["valor_anterior"] == "Prueba Antes"
        assert filas[0]["valor_nuevo"] == "Prueba Despues"

    def test_desactivar_y_activar_quedan_con_su_autor(self, session) -> None:  # noqa: ANN001
        repo = CatalogoRepository(session)
        creada = repo.crear(Area, "Prueba Estado", usuario="prueba-quien")
        repo.desactivar(Area, creada.id, usuario="prueba-uno")
        repo.activar(Area, creada.id, usuario="prueba-dos")

        acciones = [
            (f["accion"], f["usuario"])
            for f in repo.historial()
            if f["registro_id"] == creada.id
        ]
        assert ("desactivar", "prueba-uno") in acciones
        assert ("activar", "prueba-dos") in acciones

    def test_fusionar_guarda_a_donde_fue(self, session) -> None:  # noqa: ANN001
        repo = CatalogoRepository(session)
        origen = repo.crear(Area, "Prueba Origen", usuario="prueba-quien")
        destino = repo.crear(Area, "Prueba Destino", usuario="prueba-quien")
        repo.fusionar(Area, origen.id, destino.id, usuario="prueba-quien")

        filas = [
            f
            for f in repo.historial()
            if f["registro_id"] == origen.id and f["accion"] == "fusionar"
        ]
        campos = {f["campo"] for f in filas}
        assert campos == {"fusionado_en", "referencias_movidas"}
        destino_anotado = next(f for f in filas if f["campo"] == "fusionado_en")
        assert "Prueba Destino" in str(destino_anotado["valor_nuevo"])

    def test_sin_usuario_no_se_puede_cambiar_un_catalogo(self, session) -> None:  # noqa: ANN001
        with pytest.raises(ValueError, match="usuario"):
            CatalogoRepository(session).crear(Area, "Prueba Sin Autor", usuario="   ")
