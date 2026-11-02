"""Vistas con un servicio en memoria.

La base de datos no hace falta acá: lo que se prueba es el cableado de la
interfaz (que el formulario limpie, que el chip filtre, que el panel se habilite
cuando corresponde). La costura con PostgreSQL ya está cubierta en
``test_grid_integracion.py``.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from PySide6.QtCore import QDate, QItemSelectionModel
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QInputDialog,
    QMessageBox,
)

from taller.schemas.movimiento import (
    CatalogoConUso,
    CatalogoLeido,
    FechasInvalidas,
    MovimientoActualizar,
    MovimientoCrear,
    MovimientoLeido,
    ResumenEstados,
    validar_orden_fechas,
)
from taller.ui.main_window import (
    PAGINA_FORMULARIO,
    SECCION_CONFIGURACION,
    SECCION_MOVIMIENTOS,
    SECCION_REGISTRAR,
    VentanaPrincipal,
)
from taller.ui.views.configuracion_view import ConfiguracionView, PanelCatalogo
from taller.ui.views.form_registro_view import FormRegistroView
from taller.ui.views.grid_movimientos_view import GridMovimientosView
from taller.ui.views.movimiento_dialog import ANIO_MINIMO, MovimientoDialog


def fila(**extra: object) -> MovimientoLeido:
    base: dict[str, object] = {
        "id": 1,
        "estado": "en_taller",
        "fecha_entrada": dt.date(2024, 1, 10),
        "area": "Contabilidad",
        "tipo_equipo": "CPU",
        "modelo": "Dell Optiplex 3050",
        "codigo_inventario": "776",
        "soporte": ["Herrera"],
    }
    base.update(extra)
    return MovimientoLeido.model_validate(base)


class ServicioFalso:
    """In-memory double of ``ServicioTaller``."""

    def __init__(
        self, usuario: str = "operador", filas: list[MovimientoLeido] | None = None
    ) -> None:
        self.usuario = usuario
        self.filas = filas if filas is not None else [
            fila(id=1, estado="en_taller", fecha_salida=None),
            fila(
                id=2,
                estado="despachado",
                area="Prensa",
                modelo="HP ProDesk",
                fecha_salida=dt.date(2024, 2, 1),
            ),
            fila(
                id=3,
                estado="sin_datos",
                fecha_entrada=None,
                area=None,
                tipo_equipo=None,
                soporte=[],
                requiere_revision=True,
            ),
        ]
        self._areas = [
            CatalogoLeido(id=1, nombre="Contabilidad"),
            CatalogoLeido(id=2, nombre="Prensa"),
        ]
        self._tipos = [
            CatalogoLeido(id=1, nombre="CPU"),
            CatalogoLeido(id=2, nombre="Impresora"),
        ]
        self._tecnicos = [
            CatalogoLeido(id=1, nombre="Herrera"),
            CatalogoLeido(id=2, nombre="Carlos"),
        ]
        self._siguiente = 100
        self.creados: list[MovimientoCrear] = []
        self.catalogos_creados: list[tuple[str, str]] = []

    # lecturas
    def listar_movimientos(self, **filtros: object) -> list[MovimientoLeido]:
        estado = filtros.get("estado")
        solo_revision = bool(filtros.get("solo_pendientes_revision"))
        salida = []
        for f in self.filas:
            if estado is not None and f.estado != estado:
                continue
            if solo_revision and not f.requiere_revision:
                continue
            salida.append(f)
        return salida

    def resumen(self) -> ResumenEstados:
        return ResumenEstados(
            en_taller=sum(1 for f in self.filas if f.estado == "en_taller"),
            despachado=sum(1 for f in self.filas if f.estado == "despachado"),
            sin_datos=sum(1 for f in self.filas if f.estado == "sin_datos"),
            pendientes_revision=sum(1 for f in self.filas if f.requiere_revision),
        )

    def obtener(self, movimiento_id: int) -> MovimientoLeido:
        return next(f for f in self.filas if f.id == movimiento_id)

    def historial(self, movimiento_id: int) -> list[dict[str, object]]:
        return []

    def modelos_sugeridos(self, limite: int = 60) -> list[str]:
        return ["Dell Optiplex 3050", "HP ProDesk"]

    def areas(self, *, solo_activos: bool = True) -> list[CatalogoLeido]:
        return list(self._areas)

    def tecnicos(self, *, solo_activos: bool = True) -> list[CatalogoLeido]:
        return list(self._tecnicos)

    def tipos_equipo(self, *, solo_activos: bool = True) -> list[CatalogoLeido]:
        return list(self._tipos)

    def catalogo_con_uso(
        self, dimension: str, *, solo_activos: bool = False
    ) -> list[CatalogoConUso]:
        lista = {"area": self._areas, "tecnico": self._tecnicos, "tipo_equipo": self._tipos}[
            dimension
        ]
        if solo_activos:
            lista = [fila for fila in lista if fila.activo]
        conteo: dict[int, int] = {}
        for f in self.filas:
            if dimension == "area" and f.area_id:
                conteo[f.area_id] = conteo.get(f.area_id, 0) + 1
            elif dimension == "tipo_equipo" and f.tipo_equipo_id:
                conteo[f.tipo_equipo_id] = conteo.get(f.tipo_equipo_id, 0) + 1
        return [
            CatalogoConUso(
                id=fila.id,
                nombre=fila.nombre,
                activo=fila.activo,
                movimientos=conteo.get(fila.id, 0),
            )
            for fila in lista
        ]

    def _lista(self, dimension: str) -> list[CatalogoLeido]:
        return {"area": self._areas, "tecnico": self._tecnicos, "tipo_equipo": self._tipos}[
            dimension
        ]

    def renombrar_catalogo(self, dimension: str, catalogo_id: int, nombre: str) -> CatalogoLeido:
        fila = next(f for f in self._lista(dimension) if f.id == catalogo_id)
        fila.nombre = nombre.strip()
        return fila

    def desactivar_catalogo(self, dimension: str, catalogo_id: int) -> None:
        next(f for f in self._lista(dimension) if f.id == catalogo_id).activo = False

    def activar_catalogo(self, dimension: str, catalogo_id: int) -> None:
        next(f for f in self._lista(dimension) if f.id == catalogo_id).activo = True

    def fusionar_catalogo(self, dimension: str, origen_id: int, destino_id: int) -> int:
        destino = next(f for f in self._lista(dimension) if f.id == destino_id)
        movidos = 0
        for f in self.filas:
            if dimension == "area" and f.area_id == origen_id:
                f.area_id, f.area, movidos = destino_id, destino.nombre, movidos + 1
            elif dimension == "tipo_equipo" and f.tipo_equipo_id == origen_id:
                f.tipo_equipo_id, f.tipo_equipo, movidos = destino_id, destino.nombre, movidos + 1
        next(f for f in self._lista(dimension) if f.id == origen_id).activo = False
        return movidos

    def crear_catalogo(self, dimension: str, nombre: str) -> CatalogoLeido:
        self.catalogos_creados.append((dimension, nombre))
        self._siguiente += 1
        nuevo = CatalogoLeido(id=self._siguiente, nombre=nombre.strip())
        destino = {"area": self._areas, "tecnico": self._tecnicos, "tipo_equipo": self._tipos}
        destino[dimension].append(nuevo)
        return nuevo

    # escrituras
    def crear_movimiento(self, datos: MovimientoCrear) -> MovimientoLeido:
        self.creados.append(datos)
        self._siguiente += 1
        area = next((a.nombre for a in self._areas if a.id == datos.area_id), None)
        tipo = next((t.nombre for t in self._tipos if t.id == datos.tipo_equipo_id), None)
        creada = fila(
            id=self._siguiente,
            estado="en_taller" if datos.fecha_entrada else "sin_datos",
            fecha_entrada=datos.fecha_entrada,
            fecha_salida=datos.fecha_salida,
            area=area,
            tipo_equipo=tipo,
            modelo=datos.modelo,
            codigo_inventario=datos.codigo_inventario,
            diagnostico=datos.diagnostico,
            soporte=[],
        )
        self.filas.insert(0, creada)
        return creada

    def actualizar(
        self, movimiento_id: int, cambios: MovimientoActualizar, *, usuario: str | None = None
    ) -> MovimientoLeido:
        datos = cambios.model_dump(exclude_unset=True)
        actual = self.obtener(movimiento_id)
        entrada = datos.get("fecha_entrada", actual.fecha_entrada)
        salida = datos.get("fecha_salida", actual.fecha_salida)
        validar_orden_fechas(entrada, salida)  # type: ignore[arg-type]
        fusionado = actual.model_dump()
        fusionado.update(datos)
        fusionado["estado"] = (
            "despachado" if salida else "en_taller" if entrada else "sin_datos"
        )
        actualizada = MovimientoLeido.model_validate(fusionado)
        self.filas = [actualizada if f.id == movimiento_id else f for f in self.filas]
        return actualizada

    def marcar_salida(self, movimiento_id: int, fecha: dt.date | None = None) -> MovimientoLeido:
        return self.actualizar(
            movimiento_id, MovimientoActualizar(fecha_salida=fecha or dt.date.today())
        )

    def eliminar_movimiento(self, movimiento_id: int) -> None:
        self.filas = [f for f in self.filas if f.id != movimiento_id]

    def marcar_revisado(self, movimiento_id: int) -> MovimientoLeido:
        actual = self.obtener(movimiento_id)
        if actual.fecha_entrada is None:
            raise FechasInvalidas(
                "no se puede dar por revisado un registro sin fecha de entrada"
            )
        validar_orden_fechas(actual.fecha_entrada, actual.fecha_salida)
        fusionado = actual.model_dump()
        fusionado["requiere_revision"] = False
        revisada = MovimientoLeido.model_validate(fusionado)
        self.filas = [revisada if f.id == movimiento_id else f for f in self.filas]
        return revisada


class TestFormulario:
    def test_arranca_limpio_y_con_la_fecha_de_hoy(self, qtbot: object) -> None:
        form = FormRegistroView(ServicioFalso())
        qtbot.addWidget(form)  # type: ignore[attr-defined]
        assert form.area.currentIndex() == 0, "arranca en «Elegí un área…»"
        assert form.area.currentData() is None
        assert form.modelo.text() == ""
        assert form.fecha_entrada.date().toPython() == dt.date.today()
        assert form.tecnicos_marcados() == []

    def test_registrar_emite_y_limpia_para_el_siguiente(self, qtbot: object) -> None:
        servicio = ServicioFalso()
        form = FormRegistroView(servicio)
        qtbot.addWidget(form)  # type: ignore[attr-defined]

        form.area.setCurrentIndex(form.area.findData(1))
        form.tipo.setCurrentIndex(form.tipo.findData(1))
        form.modelo.setText("Dell Optiplex 3050")
        form.inventario.setText("776")

        with qtbot.waitSignal(form.movimiento_creado, timeout=1000):  # type: ignore[attr-defined]
            form.registrar()

        assert len(servicio.creados) == 1
        assert servicio.creados[0].codigo_inventario == "00776"
        assert servicio.creados[0].area_id == 1
        assert form.modelo.text() == ""
        assert form.area.currentIndex() == 0

    def test_el_area_solo_se_elige_de_la_lista(self, qtbot: object) -> None:
        # Los catálogos se administran en Configuración: acá no se escribe texto.
        servicio = ServicioFalso()
        form = FormRegistroView(servicio)
        qtbot.addWidget(form)  # type: ignore[attr-defined]

        assert not form.area.isEditable(), "no debe aceptar texto libre"
        assert not form.tipo.isEditable()
        assert form.area.count() == len(servicio.areas()) + 1, "marcador + opciones"
        assert form.datos().area_id is None, "sin elegir queda vacío"
        assert servicio.catalogos_creados == [], "el formulario no crea catálogos"

    def test_elegir_un_area_guarda_su_id(self, qtbot: object) -> None:
        servicio = ServicioFalso()
        form = FormRegistroView(servicio)
        qtbot.addWidget(form)  # type: ignore[attr-defined]
        posicion = form.area.findText("Contabilidad")
        form.area.setCurrentIndex(posicion)
        assert form.datos().area_id == 1

    def test_el_atajo_ctrl_enter_esta_registrado(self, qtbot: object) -> None:
        # Se verifica el registro del atajo y no la pulsación: con la plataforma
        # offscreen el foco de teclado no es confiable, y un test que depende del
        # foco falla por la razón equivocada.
        form = FormRegistroView(ServicioFalso())
        qtbot.addWidget(form)  # type: ignore[attr-defined]
        esperado = QKeySequence("Ctrl+Return")
        atajos = [atajo.key() for atajo in form.findChildren(QShortcut)]
        assert esperado in atajos

    def test_los_soportes_se_marcan_y_se_leen(self, qtbot: object) -> None:
        form = FormRegistroView(ServicioFalso())
        qtbot.addWidget(form)  # type: ignore[attr-defined]
        assert len(form._chips_soporte) == 2
        form._chips_soporte[1].setChecked(True)
        form._chips_soporte[2].setChecked(True)
        assert form.tecnicos_marcados() == [1, 2]
        assert form.datos().tecnicos == [1, 2]


def seleccionar_por_id(grid: GridMovimientosView, movimiento_id: int) -> None:
    """Select a row by its id.

    The proxy sorts by intake date, so a visible row number is not a model row
    number. Tests that assumed the source order were asserting the wrong thing.
    """
    modelo = grid.tabla.model()
    for visual in range(modelo.rowCount()):
        origen = modelo.mapToSource(modelo.index(visual, 0))
        if grid._modelo.fila(origen.row()).id == movimiento_id:
            grid.tabla.selectRow(visual)
            return
    raise AssertionError(f"no se encontró el movimiento {movimiento_id}")


class TestGrid:
    def _grid(self, qtbot: object, servicio: ServicioFalso | None = None) -> GridMovimientosView:
        vista = GridMovimientosView(servicio or ServicioFalso(), "operador")
        qtbot.addWidget(vista)  # type: ignore[attr-defined]
        return vista

    def test_carga_las_filas_y_los_contadores(self, qtbot: object) -> None:
        grid = self._grid(qtbot)
        assert grid.tabla.model().rowCount() == 3
        assert grid.chips["Todos"].text() == "Todos · 3"
        assert grid.chips["Requiere revisión"].text() == "Requiere revisión · 1"

    def test_el_buscador_filtra(self, qtbot: object) -> None:
        grid = self._grid(qtbot)
        grid.busqueda.setText("prensa")
        grid._aplicar_busqueda()
        assert grid.tabla.model().rowCount() == 1

    def test_los_chips_filtran_por_estado(self, qtbot: object) -> None:
        grid = self._grid(qtbot)
        grid.chips["Despachados"].setChecked(True)
        grid._aplicar_chip()
        assert grid.tabla.model().rowCount() == 1

    def test_el_chip_de_revision_filtra_las_marcadas(self, qtbot: object) -> None:
        grid = self._grid(qtbot)
        grid.mostrar_solo_revision()
        assert grid.tabla.model().rowCount() == 1

    def test_el_panel_muestra_la_fila_seleccionada(self, qtbot: object) -> None:
        grid = self._grid(qtbot)
        seleccionar_por_id(grid, 2)
        fila_actual = grid.fila_seleccionada()
        assert fila_actual is not None
        assert "Despachado" in grid._badge.text()
        assert grid._valores["modelo"].text() == "HP ProDesk"

    def test_el_boton_de_salida_se_habilita_solo_si_no_esta_despachado(
        self, qtbot: object
    ) -> None:
        grid = self._grid(qtbot)
        seleccionar_por_id(grid, 1)
        assert grid.boton_salida.isEnabled()
        seleccionar_por_id(grid, 2)
        assert not grid.boton_salida.isEnabled()

    def test_el_boton_de_revisado_espera_fechas_consistentes(self, qtbot: object) -> None:
        servicio = ServicioFalso(
            filas=[
                fila(
                    id=9,
                    estado="despachado",
                    fecha_entrada=dt.date(2024, 5, 1),
                    fecha_salida=dt.date(2024, 4, 1),
                    requiere_revision=True,
                )
            ]
        )
        grid = self._grid(qtbot, servicio)
        grid.tabla.selectRow(0)
        assert not grid.boton_revisado.isEnabled(), "fechas invertidas no se pueden liberar"

    def test_marcar_salida_actualiza_la_fila(
        self, qtbot: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
        servicio = ServicioFalso()
        grid = self._grid(qtbot, servicio)
        seleccionar_por_id(grid, 1)
        with qtbot.waitSignal(grid.mensaje, timeout=1000):  # type: ignore[attr-defined]
            grid.marcar_salida()
        assert servicio.obtener(1).estado == "despachado"

    def test_marcar_salida_cancelada_no_toca_nada(
        self, qtbot: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Cancel
        )
        servicio = ServicioFalso()
        grid = self._grid(qtbot, servicio)
        seleccionar_por_id(grid, 1)
        grid.marcar_salida()
        assert servicio.obtener(1).estado == "en_taller"

    def test_una_fila_sin_fechas_no_se_puede_dar_por_revisada(self, qtbot: object) -> None:
        servicio = ServicioFalso(
            filas=[
                fila(
                    id=11,
                    estado="sin_datos",
                    fecha_entrada=None,
                    fecha_salida=None,
                    requiere_revision=True,
                )
            ]
        )
        grid = self._grid(qtbot, servicio)
        grid.tabla.selectRow(0)
        assert not grid.boton_revisado.isEnabled()
        with qtbot.waitSignal(grid.error_validacion, timeout=1000):  # type: ignore[attr-defined]
            grid.marcar_revisado()

    def test_marcar_revisado_limpia_la_marca(self, qtbot: object) -> None:
        servicio = ServicioFalso(
            filas=[fila(id=7, estado="en_taller", fecha_salida=None, requiere_revision=True)]
        )
        grid = self._grid(qtbot, servicio)
        grid.tabla.selectRow(0)
        assert grid.boton_revisado.isEnabled()
        with qtbot.waitSignal(grid.mensaje, timeout=1000):  # type: ignore[attr-defined]
            grid.marcar_revisado()
        assert servicio.obtener(7).requiere_revision is False

    def test_una_revision_imposible_reporta_el_motivo(self, qtbot: object) -> None:
        servicio = ServicioFalso(
            filas=[
                fila(
                    id=8,
                    estado="despachado",
                    fecha_entrada=dt.date(2024, 5, 1),
                    fecha_salida=dt.date(2024, 4, 1),
                    requiere_revision=True,
                )
            ]
        )
        grid = self._grid(qtbot, servicio)
        grid.tabla.selectRow(0)
        with qtbot.waitSignal(grid.error_validacion, timeout=1000):  # type: ignore[attr-defined]
            grid.marcar_revisado()

    def test_el_contador_dice_cuantas_filas_se_estan_viendo(self, qtbot: object) -> None:
        # El chip cuenta en la base; sin este contador, "Requiere revisión · 14"
        # sobre una tabla vacía parece que se perdieron los datos.
        grid = self._grid(qtbot)
        assert grid.visibles.text() == "3 filas"
        grid.busqueda.setText("prensa")
        grid._aplicar_busqueda()
        assert grid.visibles.text() == "1 de 3 filas"

    def test_agregar_inserta_sin_recargar(self, qtbot: object) -> None:
        servicio = ServicioFalso()
        grid = self._grid(qtbot, servicio)
        nueva = fila(id=50, estado="en_taller", modelo="Nuevo")
        servicio.filas.append(nueva)  # el servicio real ya la tendría
        grid.agregar(nueva)
        assert grid.tabla.model().rowCount() == 4
        assert grid.chips["Todos"].text() == "Todos · 4"


class TestVentanaPrincipal:
    def test_abre_en_el_formulario(self, qtbot: object) -> None:
        ventana = VentanaPrincipal(ServicioFalso())
        qtbot.addWidget(ventana)  # type: ignore[attr-defined]
        assert ventana.seccion_actual == SECCION_REGISTRAR
        assert ventana.pagina_actual == PAGINA_FORMULARIO

    def test_el_rail_cambia_de_pagina(self, qtbot: object) -> None:
        ventana = VentanaPrincipal(ServicioFalso())
        qtbot.addWidget(ventana)  # type: ignore[attr-defined]
        ventana.ir_a(SECCION_MOVIMIENTOS)
        assert ventana.seccion_actual == SECCION_MOVIMIENTOS
        ventana.ir_a(SECCION_CONFIGURACION)
        assert ventana.seccion_actual == SECCION_CONFIGURACION

    def test_la_revision_sigue_accesible_como_chip(self, qtbot: object) -> None:
        # Salió del rail, no del producto: las filas marcadas se trabajan acá.
        ventana = VentanaPrincipal(ServicioFalso())
        qtbot.addWidget(ventana)  # type: ignore[attr-defined]
        assert ventana.grid.chips["Requiere revisión"].text() == "Requiere revisión · 1"
        ventana.grid.mostrar_solo_revision()
        assert ventana.grid.esta_filtrando_revision()

    def test_registrar_deja_la_fila_en_el_grid_sin_cambiar_de_pagina(
        self, qtbot: object
    ) -> None:
        ventana = VentanaPrincipal(ServicioFalso())
        qtbot.addWidget(ventana)  # type: ignore[attr-defined]
        ventana.formulario.registrar()
        assert ventana.seccion_actual == SECCION_REGISTRAR
        assert ventana.seccion_actual == SECCION_REGISTRAR, "seguimos en la casa"
        assert ventana.grid.tabla.model().rowCount() == 4

    def test_el_estado_muestra_el_total_y_el_usuario(self, qtbot: object) -> None:
        ventana = VentanaPrincipal(ServicioFalso())
        qtbot.addWidget(ventana)  # type: ignore[attr-defined]
        assert "3 registros" in ventana._total.text()
        assert ventana._usuario.text() == "operador"


class TestConfiguracion:
    """Las tres pestañas y sus cuatro acciones."""

    def _vista(self, qtbot: object, servicio: ServicioFalso | None = None) -> ConfiguracionView:
        vista = ConfiguracionView(servicio or ServicioFalso())
        qtbot.addWidget(vista)  # type: ignore[attr-defined]
        return vista

    @staticmethod
    def _seleccionar(panel: PanelCatalogo, *posiciones: int) -> None:
        modelo = panel.tabla.selectionModel()
        modelo.clearSelection()
        for posicion in posiciones:
            modelo.select(
                panel.tabla.model().index(posicion, 0),
                QItemSelectionModel.SelectionFlag.Select
                | QItemSelectionModel.SelectionFlag.Rows,
            )

    def test_cinco_pestanas_con_sus_paneles(self, qtbot: object) -> None:
        vista = self._vista(qtbot)
        assert vista.pestanas.count() == 5
        assert vista.pestanas.tabText(3) == "Administración"
        assert vista.pestanas.tabText(4) == "Sistema"
        assert set(vista.paneles) == {"tipo_equipo", "area", "tecnico"}

    def test_lista_con_el_uso_de_cada_fila(self, qtbot: object) -> None:
        servicio = ServicioFalso(
            filas=[
                fila(id=1, area_id=1, area="Contabilidad"),
                fila(id=2, area_id=1, area="Contabilidad"),
            ]
        )
        vista = self._vista(qtbot, servicio)
        areas = vista.panel("area")._modelo.filas()
        contabilidad = next(a for a in areas if a.nombre == "Contabilidad")
        assert contabilidad.movimientos == 2

    def test_crear_un_registro(self, qtbot: object, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Climatología", True))
        servicio = ServicioFalso()
        vista = self._vista(qtbot, servicio)
        with qtbot.waitSignal(vista.catalogo_cambiado, timeout=1000):  # type: ignore[attr-defined]
            vista.panel("area").nuevo()
        assert ("area", "Climatología") in servicio.catalogos_creados

    def test_renombrar(self, qtbot: object, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Contaduría", True))
        servicio = ServicioFalso()
        vista = self._vista(qtbot, servicio)
        panel = vista.panel("area")
        self._seleccionar(panel, 0)
        panel.renombrar()
        assert servicio._areas[0].nombre == "Contaduría"

    def test_desactivar_pide_confirmacion(
        self, qtbot: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
        )
        servicio = ServicioFalso()
        vista = self._vista(qtbot, servicio)
        panel = vista.panel("area")
        self._seleccionar(panel, 0)
        panel.desactivar()
        assert servicio._areas[0].activo is False

    def test_desactivar_cancelado_no_cambia_nada(
        self, qtbot: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Cancel
        )
        servicio = ServicioFalso()
        vista = self._vista(qtbot, servicio)
        panel = vista.panel("area")
        self._seleccionar(panel, 0)
        panel.desactivar()
        assert servicio._areas[0].activo is True

    def test_fusionar_necesita_exactamente_dos_filas(self, qtbot: object) -> None:
        vista = self._vista(qtbot)
        panel = vista.panel("area")
        assert not panel.boton_fusionar.isEnabled()
        self._seleccionar(panel, 0)
        assert not panel.boton_fusionar.isEnabled()
        self._seleccionar(panel, 0, 1)
        assert panel.boton_fusionar.isEnabled()

    def test_fusionar_deja_viva_la_fila_con_mas_historial(
        self, qtbot: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Contabilidad tiene dos movimientos; Prensa ninguno. Sin importar el
        # orden de selección, Prensa se absorbe en Contabilidad.
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
        servicio = ServicioFalso(
            filas=[
                fila(id=1, area_id=1, area="Contabilidad"),
                fila(id=2, area_id=1, area="Contabilidad"),
            ]
        )
        vista = self._vista(qtbot, servicio)
        panel = vista.panel("area")
        prensa = next(pos for pos, a in enumerate(panel._modelo.filas()) if a.nombre == "Prensa")
        contabilidad = next(
            pos for pos, a in enumerate(panel._modelo.filas()) if a.nombre == "Contabilidad"
        )
        self._seleccionar(panel, prensa, contabilidad)

        with qtbot.waitSignal(vista.catalogo_cambiado, timeout=1000):  # type: ignore[attr-defined]
            panel.fusionar()

        activas = [a.nombre for a in panel._modelo.filas() if a.activo]
        assert "Contabilidad" in activas
        assert "Prensa" not in activas

    def test_un_registro_desactivado_sigue_visible(self, qtbot: object) -> None:
        # Si desaparece, no hay forma de reactivarlo sin tocar SQL.
        servicio = ServicioFalso()
        servicio._areas.append(CatalogoLeido(id=99, nombre="Vieja", activo=False))
        vista = self._vista(qtbot, servicio)
        filas = vista.panel("area")._modelo.filas()
        inactiva = next((a for a in filas if a.nombre == "Vieja"), None)
        assert inactiva is not None, "la fila inactiva desapareció de la lista"
        assert inactiva.activo is False

    def test_reactivar_una_fila_inactiva(self, qtbot: object) -> None:
        # Desactivar sin vuelta atrás sería una trampa: el botón alterna.
        servicio = ServicioFalso()
        servicio._areas.append(CatalogoLeido(id=99, nombre="Vieja", activo=False))
        vista = self._vista(qtbot, servicio)
        panel = vista.panel("area")
        posicion = next(
            pos for pos, a in enumerate(panel._modelo.filas()) if a.nombre == "Vieja"
        )
        self._seleccionar(panel, posicion)
        assert panel.boton_desactivar.text() == "Reactivar"

        panel.alternar_activo()

        reactivada = next(a for a in servicio._areas if a.id == 99)
        assert reactivada.activo is True


class TestExportacion:
    """El botón vive solo en Movimientos y exporta lo que se está viendo."""

    def _grid(self, qtbot: object, servicio: ServicioFalso | None = None) -> GridMovimientosView:
        vista = GridMovimientosView(servicio or ServicioFalso(), "operador")
        qtbot.addWidget(vista)  # type: ignore[attr-defined]
        return vista

    def test_exporta_solo_las_filas_visibles(self, qtbot: object, tmp_path: Path) -> None:
        grid = self._grid(qtbot)
        grid.busqueda.setText("prensa")
        grid._aplicar_busqueda()
        assert len(grid.filas_visibles()) == 1

        destino = grid.exportar_csv(tmp_path / "filtrado.csv")

        assert destino is not None
        texto = destino.read_text(encoding="utf-8-sig")
        lineas = [linea for linea in texto.splitlines() if linea]
        assert len(lineas) == 2, "encabezado más la única fila filtrada"
        assert "Prensa" in lineas[1]

    def test_el_boton_pide_la_ruta_y_escribe(
        self, qtbot: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        destino = tmp_path / "elegido.csv"
        monkeypatch.setattr(
            QFileDialog, "getSaveFileName", lambda *a, **k: (str(destino), "")
        )
        grid = self._grid(qtbot)
        with qtbot.waitSignal(grid.mensaje, timeout=1000) as señal:  # type: ignore[attr-defined]
            grid.boton_exportar.click()
        assert destino.is_file()
        assert "3 movimientos exportados" in señal.args[0]

    def test_cancelar_el_dialogo_no_escribe_nada(
        self, qtbot: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
        grid = self._grid(qtbot)
        assert grid.exportar_csv() is None

    def test_sin_filas_avisa_y_no_crea_archivo(
        self, qtbot: object, tmp_path: Path
    ) -> None:
        grid = self._grid(qtbot)
        grid.busqueda.setText("no existe nada con este texto")
        grid._aplicar_busqueda()
        destino = tmp_path / "vacio.csv"
        with qtbot.waitSignal(grid.error_validacion, timeout=1000):  # type: ignore[attr-defined]
            assert grid.exportar_csv(destino) is None
        assert not destino.exists()

    def test_el_formulario_no_tiene_exportacion(self, qtbot: object) -> None:
        # El pedido era explícito: solo en la ventana donde se ven todos.
        ventana = VentanaPrincipal(ServicioFalso())
        qtbot.addWidget(ventana)  # type: ignore[attr-defined]
        assert not hasattr(ventana.formulario, "boton_exportar")
        assert hasattr(ventana.grid, "boton_exportar")
        assert not hasattr(ventana.configuracion, "boton_exportar")


class TestVentanaDeEdicion:
    """El doble clic abre una ventana; la celda ya no se edita in situ."""

    def _dialogo(self, qtbot: object, servicio: ServicioFalso, movimiento_id: int = 1):
        fila_actual = servicio.obtener(movimiento_id)
        dialogo = MovimientoDialog(servicio, fila_actual)
        qtbot.addWidget(dialogo)  # type: ignore[attr-defined]
        return dialogo

    def test_carga_los_valores_actuales(self, qtbot: object) -> None:
        # La fila necesita los ids de catálogo, que es lo que la vista guarda.
        servicio = ServicioFalso(
            filas=[
                fila(
                    id=1,
                    area_id=1,
                    tipo_equipo_id=1,
                    estado="en_taller",
                    fecha_salida=None,
                )
            ]
        )
        dialogo = self._dialogo(qtbot, servicio)
        assert dialogo.modelo.text() == "Dell Optiplex 3050"
        assert dialogo.area.currentText() == "Contabilidad"
        assert dialogo.fecha_entrada.date().toPython() == dt.date(2024, 1, 10)
        assert dialogo.fecha_salida.date().toPython() == dt.date(ANIO_MINIMO, 1, 1)
        assert dialogo._tecnicos_marcados() == [1]

    def test_muestra_la_referencia_del_registro(self, qtbot: object) -> None:
        servicio = ServicioFalso()
        dialogo = self._dialogo(qtbot, servicio)
        assert "línea" in dialogo._referencia() or "aplicación" in dialogo._referencia()

    def test_devuelve_solo_los_cambios(self, qtbot: object) -> None:
        servicio = ServicioFalso()
        dialogo = self._dialogo(qtbot, servicio)
        dialogo.nota.setPlainText("nota desde la ventana")
        cambios = dialogo.cambios()
        assert cambios.nota == "nota desde la ventana"

    def test_el_codigo_se_normaliza_al_guardar(self, qtbot: object) -> None:
        servicio = ServicioFalso()
        dialogo = self._dialogo(qtbot, servicio)
        dialogo.inventario.setText("1716")
        assert dialogo.cambios().codigo_inventario == "01716"

    def test_guardar_aplica_y_devuelve_el_registro(self, qtbot: object) -> None:
        servicio = ServicioFalso()
        dialogo = self._dialogo(qtbot, servicio)
        dialogo.nota.setPlainText("guardada")
        actualizado = dialogo.guardar()
        assert actualizado is not None
        assert actualizado.nota == "guardada"
        assert servicio.obtener(1).nota == "guardada"

    def test_una_fecha_invertida_muestra_el_error_y_no_cierra(self, qtbot: object) -> None:
        servicio = ServicioFalso()
        dialogo = self._dialogo(qtbot, servicio)
        dialogo.fecha_salida.setDate(QDate(2023, 1, 1))
        assert dialogo.guardar() is None
        assert not dialogo.error.isHidden()
        assert "anterior" in dialogo.error.text()

    def test_los_soportes_se_pueden_marcar_y_desmarcar(self, qtbot: object) -> None:
        servicio = ServicioFalso()
        dialogo = self._dialogo(qtbot, servicio)
        dialogo._chips[2].setChecked(True)
        assert dialogo._tecnicos_marcados() == [1, 2]
        dialogo._chips[1].setChecked(False)
        assert dialogo._tecnicos_marcados() == [2]


class TestDobleClicEnElGrid:
    def test_el_grid_no_edita_celdas(self, qtbot: object) -> None:
        grid = GridMovimientosView(ServicioFalso(), "operador")
        qtbot.addWidget(grid)  # type: ignore[attr-defined]
        assert (
            grid.tabla.editTriggers()
            == QAbstractItemView.EditTrigger.NoEditTriggers
        ), "el grid no debe permitir editar la celda directamente"

    def test_el_doble_clic_abre_la_ventana_y_aplica_el_cambio(
        self, qtbot: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        servicio = ServicioFalso()
        grid = GridMovimientosView(servicio, "operador")
        qtbot.addWidget(grid)  # type: ignore[attr-defined]

        abiertos: list[int] = []

        class DialogoFalso:
            def __init__(self, _servicio: object, fila: object, _padre: object) -> None:
                abiertos.append(fila.id)  # type: ignore[attr-defined]
                cambios = servicio.actualizar(
                    fila.id,  # type: ignore[attr-defined]
                    MovimientoActualizar(nota="editada en la ventana"),
                )
                self.actualizado = cambios

            def exec(self) -> int:
                return QDialog.DialogCode.Accepted

        monkeypatch.setattr(
            "taller.ui.views.grid_movimientos_view.MovimientoDialog", DialogoFalso
        )
        seleccionar_por_id(grid, 1)

        with qtbot.waitSignal(grid.mensaje, timeout=1000):  # type: ignore[attr-defined]
            grid.editar_seleccionado()

        assert abiertos, "no se abrió la ventana de edición"
        assert any(f.nota == "editada en la ventana" for f in servicio.filas)


class TestAdministracion:
    """El borrado definitivo vive en Configuración y pide dos confirmaciones."""

    def _vista(self, qtbot: object, servicio: ServicioFalso | None = None):
        # Se devuelve la ventana entera: si solo se devuelve el panel, el widget
        # raíz se queda sin referencia de Python y Qt lo destruye.
        servicio = servicio or ServicioFalso()
        vista = ConfiguracionView(servicio)
        qtbot.addWidget(vista)  # type: ignore[attr-defined]
        return vista, servicio

    def test_sin_modo_administrador_no_se_puede_eliminar(self, qtbot: object) -> None:
        vista, _servicio = self._vista(qtbot)
        panel = vista.administracion
        panel.tabla.selectRow(0)
        assert not panel.boton_eliminar.isEnabled()
        assert panel.eliminar() is False

    def test_con_modo_y_seleccion_se_habilita(self, qtbot: object) -> None:
        vista, _servicio = self._vista(qtbot)
        panel = vista.administracion
        panel.modo_admin.setChecked(True)
        assert not panel.boton_eliminar.isEnabled(), "sin selección no alcanza"
        panel.tabla.selectRow(0)
        assert panel.boton_eliminar.isEnabled()

    def test_una_confirmacion_distinta_no_borra(
        self, qtbot: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("no coincide", True))
        vista, servicio = self._vista(qtbot)
        panel = vista.administracion
        panel.modo_admin.setChecked(True)
        panel.tabla.selectRow(0)
        filas_antes = len(servicio.filas)

        assert panel.eliminar() is False
        assert len(servicio.filas) == filas_antes

    def test_cancelar_el_dialogo_no_borra(
        self, qtbot: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("776", False))
        vista, servicio = self._vista(qtbot)
        panel = vista.administracion
        panel.modo_admin.setChecked(True)
        panel.tabla.selectRow(0)
        filas_antes = len(servicio.filas)
        panel.eliminar()
        assert len(servicio.filas) == filas_antes

    def test_confirmando_el_codigo_se_elimina(
        self, qtbot: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("776", True))
        vista, servicio = self._vista(qtbot)
        panel = vista.administracion
        panel.modo_admin.setChecked(True)
        panel.tabla.selectRow(0)

        with qtbot.waitSignal(vista.catalogo_cambiado, timeout=1000):  # type: ignore[attr-defined]
            assert panel.eliminar() is True

        assert all(f.id != 1 for f in servicio.filas)
        assert panel.tabla.model().rowCount() == 2


class TestPanelSistema:
    """La configuración del instalador tiene que seguir siendo alcanzable."""

    def _panel(self, qtbot: object):
        from taller.ui.views.configuracion_view import PanelSistema

        panel = PanelSistema()
        qtbot.addWidget(panel)  # type: ignore[attr-defined]
        return panel

    def test_sin_configuracion_lo_dice(self, qtbot: object, monkeypatch) -> None:
        import taller.ui.views.configuracion_view as modulo

        monkeypatch.setattr(
            modulo,
            "cargar_configuracion",
            lambda **_k: __import__(
                "taller.arranque", fromlist=["ConfiguracionArranque"]
            ).ConfiguracionArranque(),
        )
        panel = self._panel(qtbot)
        assert panel._valores["nombre"].text() == "sin configurar"
        assert panel._valores["servidor"].text() == "sin configurar"

    def test_muestra_la_configuracion_guardada_sin_contrasena(
        self, qtbot: object, monkeypatch
    ) -> None:
        import taller.ui.views.configuracion_view as modulo
        from taller.arranque import ConfiguracionArranque

        guardada = ConfiguracionArranque(
            database_url="postgresql+psycopg://ana:secreta@servidor:5433/taller",
            nombre="Mi Taller",
            organizacion="Mi Org",
        )
        monkeypatch.setattr(modulo, "cargar_configuracion", lambda **_k: guardada)
        panel = self._panel(qtbot)
        assert panel._valores["nombre"].text() == "Mi Taller"
        assert panel._valores["servidor"].text() == "servidor:5433"
        assert panel._valores["base"].text() == "taller"
        assert panel._valores["usuario"].text() == "ana"
        # la contraseña nunca se muestra
        assert all("secreta" not in v.text() for v in panel._valores.values())

    def test_abrir_la_configuracion_y_guardar_avisa_y_emite(
        self, qtbot: object, monkeypatch
    ) -> None:
        from PySide6.QtWidgets import QDialog

        import taller.ui.views.configuracion_inicial as modulo_dialogo

        class DialogoFalso:
            def __init__(self, *_a, **_k) -> None:
                pass

            def exec(self) -> int:
                return QDialog.DialogCode.Accepted

        monkeypatch.setattr(modulo_dialogo, "ConfiguracionInicialDialog", DialogoFalso)
        panel = self._panel(qtbot)

        with qtbot.waitSignal(panel.configuracion_cambiada, timeout=1000):  # type: ignore[attr-defined]
            assert panel.abrir_configuracion() is True

        assert not panel.aviso.isHidden()

    def test_cancelar_no_emite_nada(self, qtbot: object, monkeypatch) -> None:
        from PySide6.QtWidgets import QDialog

        import taller.ui.views.configuracion_inicial as modulo_dialogo

        class DialogoFalso:
            def __init__(self, *_a, **_k) -> None:
                pass

            def exec(self) -> int:
                return QDialog.DialogCode.Rejected

        monkeypatch.setattr(modulo_dialogo, "ConfiguracionInicialDialog", DialogoFalso)
        panel = self._panel(qtbot)
        assert panel.abrir_configuracion() is False
