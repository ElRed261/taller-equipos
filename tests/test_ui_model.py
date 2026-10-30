"""The Qt layer: table model, search proxy and cell delegates.

These tests run without a database. The model talks to a persistence double, and
the double applies the same real rule the repository applies (``validar_orden_fechas``),
so a green test here means the model really refuses bad dates.
"""

from __future__ import annotations

import datetime as dt

import pytest
from PySide6.QtCore import QDate, QModelIndex, QRect, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QComboBox, QDateEdit, QStyleOptionViewItem

from taller.schemas.movimiento import (
    CatalogoLeido,
    MovimientoActualizar,
    MovimientoLeido,
    validar_orden_fechas,
)
from taller.ui.delegates.grid_delegates import (
    FECHA_VACIA,
    ComboDelegate,
    FechaDelegate,
    SemaforoDelegate,
    delegate_por_columna,
)
from taller.ui.models.filtro_movimientos import FiltroMovimientos, filtrar
from taller.ui.models.movimientos_table_model import (
    COLOR_ESTADO,
    COLUMNAS,
    Columna,
    MovimientosTableModel,
)

USUARIO = "operador"


def fila(**extra: object) -> MovimientoLeido:
    base: dict[str, object] = {
        "id": 1,
        "estado": "en_taller",
        "fecha_entrada": dt.date(2024, 1, 10),
        "area": "Agrometeorología",
        "tipo_equipo": "CPU",
        "modelo": "Dell Optiplex 3050",
        "codigo_inventario": "776",
        "soporte": ["Herrera"],
    }
    base.update(extra)
    return MovimientoLeido.model_validate(base)


class PersistenciaFalsa:
    """Stands in for ``MovimientoRepository`` without a database."""

    def __init__(self, *filas: MovimientoLeido) -> None:
        self.filas = {fila.id: fila for fila in filas}
        self.llamadas: list[tuple[int, dict[str, object]]] = []

    def actualizar(
        self, movimiento_id: int, cambios: MovimientoActualizar, *, usuario: str
    ) -> MovimientoLeido:
        datos = cambios.model_dump(exclude_unset=True)
        self.llamadas.append((movimiento_id, datos))

        actual = self.filas[movimiento_id]
        entrada = datos.get("fecha_entrada", actual.fecha_entrada)
        salida = datos.get("fecha_salida", actual.fecha_salida)
        validar_orden_fechas(entrada, salida)  # type: ignore[arg-type]

        fusionado = actual.model_dump()
        fusionado.update(datos)
        fusionado["estado"] = (
            "despachado"
            if salida is not None
            else "en_taller"
            if entrada is not None
            else "sin_datos"
        )
        if "area_id" in datos:
            fusionado["area"] = "(nueva área)" if datos["area_id"] else None
        actualizada = MovimientoLeido.model_validate(fusionado)
        self.filas[movimiento_id] = actualizada
        return actualizada


@pytest.fixture
def modelo(qtbot: object) -> MovimientosTableModel:
    dobles = PersistentDobleFactory()
    return MovimientosTableModel(dobles.persistencia, usuario=USUARIO, filas=dobles.filas)


class PersistentDobleFactory:
    """Three rows covering the three derived states."""

    def __init__(self) -> None:
        self.filas = [
            fila(id=1, estado="en_taller", fecha_salida=None),
            fila(
                id=2,
                estado="despachado",
                fecha_entrada=dt.date(2023, 12, 31),
                fecha_salida=dt.date(2024, 2, 1),
                area="Contabilidad",
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
        self.persistencia = PersistenciaFalsa(*self.filas)


class TestEstructura:
    def test_counts_match_the_column_contract(self, modelo: MovimientosTableModel) -> None:
        assert modelo.rowCount() == 3
        assert modelo.columnCount() == len(COLUMNAS) == len(Columna)

    def test_headers(self, modelo: MovimientosTableModel) -> None:
        assert modelo.headerData(Columna.FECHA_ENTRADA, Qt.Orientation.Horizontal) == "Entrada"
        assert modelo.headerData(Columna.INVENTARIO, Qt.Orientation.Horizontal) == "Inventario"

    def test_an_invalid_index_returns_nothing(self, modelo: MovimientosTableModel) -> None:
        assert modelo.data(QModelIndex()) is None


class TestVisualizacion:
    def test_dates_are_shown_as_dd_mm_aaaa_without_hours(
        self, modelo: MovimientosTableModel
    ) -> None:
        texto = modelo.data(modelo.index(0, Columna.FECHA_ENTRADA))
        assert texto == "10/01/2024"
        assert ":" not in texto

    def test_an_empty_departure_date_shows_nothing(self, modelo: MovimientosTableModel) -> None:
        assert modelo.data(modelo.index(0, Columna.FECHA_SALIDA)) == ""

    def test_the_state_column_has_no_text_so_the_badge_speaks(
        self, modelo: MovimientosTableModel
    ) -> None:
        indice = modelo.index(0, Columna.ESTADO)
        assert modelo.data(indice, Qt.ItemDataRole.DisplayRole) == ""
        assert modelo.data(indice, Qt.ItemDataRole.UserRole) == "en_taller"

    def test_each_state_has_its_own_icon(self, modelo: MovimientosTableModel) -> None:
        iconos = [
            modelo.data(modelo.index(numero, Columna.ESTADO), Qt.ItemDataRole.DecorationRole)
            for numero in range(3)
        ]
        assert all(isinstance(icono, QIcon) for icono in iconos)
        assert len({icono.cacheKey() for icono in iconos}) == 3

    def test_the_state_tooltip_explains_itself(self, modelo: MovimientosTableModel) -> None:
        assert "desde el 10/01/2024" in modelo.data(
            modelo.index(0, Columna.ESTADO), Qt.ItemDataRole.ToolTipRole
        )
        assert "Despachado el 01/02/2024" in modelo.data(
            modelo.index(1, Columna.ESTADO), Qt.ItemDataRole.ToolTipRole
        )
        assert "no tiene fechas" in modelo.data(
            modelo.index(2, Columna.ESTADO), Qt.ItemDataRole.ToolTipRole
        )

    def test_the_review_flag_is_visible_and_explained(self, modelo: MovimientosTableModel) -> None:
        assert modelo.data(modelo.index(2, Columna.REVISION)) == "⚠"
        assert modelo.data(modelo.index(0, Columna.REVISION)) == ""

    def test_technicians_are_joined_in_one_cell(self, qtbot: object) -> None:
        modelo = MovimientosTableModel(
            PersistenciaFalsa(), usuario=USUARIO, filas=[fila(soporte=["Herrera", "Carlos"])]
        )
        assert modelo.data(modelo.index(0, Columna.SOPORTE)) == "Herrera, Carlos"


class TestEditabilidad:
    def test_the_state_column_cannot_be_edited(self, modelo: MovimientosTableModel) -> None:
        flags = modelo.flags(modelo.index(0, Columna.ESTADO))
        assert not flags & Qt.ItemFlag.ItemIsEditable
        assert not modelo.setData(modelo.index(0, Columna.ESTADO), "despachado")

    def test_technicians_and_state_are_read_only(self, modelo: MovimientosTableModel) -> None:
        for columna in (Columna.SOPORTE, Columna.REVISION):
            assert not modelo.flags(modelo.index(0, columna)) & Qt.ItemFlag.ItemIsEditable

    def test_text_columns_are_editable(self, modelo: MovimientosTableModel) -> None:
        for columna in (
            Columna.FECHA_ENTRADA,
            Columna.AREA,
            Columna.MODELO,
            Columna.INVENTARIO,
            Columna.NOTA,
        ):
            assert modelo.flags(modelo.index(0, columna)) & Qt.ItemFlag.ItemIsEditable


class TestEdicion:
    def test_a_valid_edit_is_persisted_and_reflected(
        self, qtbot: object
    ) -> None:
        dobles = PersistentDobleFactory()
        modelo = MovimientosTableModel(dobles.persistencia, usuario=USUARIO, filas=dobles.filas)

        with qtbot.waitSignal(modelo.movimiento_actualizado, timeout=1000):  # type: ignore[attr-defined]
            resultado = modelo.setData(
                modelo.index(0, Columna.FECHA_SALIDA), dt.date(2024, 1, 15)
            )

        assert resultado is True
        assert modelo.data(modelo.index(0, Columna.FECHA_SALIDA)) == "15/01/2024"
        assert dobles.persistencia.llamadas == [(1, {"fecha_salida": dt.date(2024, 1, 15)})]

    def test_setting_the_departure_date_flips_the_badge(self, qtbot: object) -> None:
        dobles = PersistentDobleFactory()
        modelo = MovimientosTableModel(dobles.persistencia, usuario=USUARIO, filas=dobles.filas)
        indice = modelo.index(0, Columna.ESTADO)
        assert modelo.data(indice, Qt.ItemDataRole.UserRole) == "en_taller"

        modelo.setData(modelo.index(0, Columna.FECHA_SALIDA), dt.date(2024, 1, 15))

        assert modelo.data(indice, Qt.ItemDataRole.UserRole) == "despachado"

    def test_an_inverted_date_is_refused_and_the_row_is_untouched(
        self, qtbot: object, modelo: MovimientosTableModel
    ) -> None:
        with qtbot.waitSignal(modelo.error_validacion, timeout=1000) as señal:  # type: ignore[attr-defined]
            resultado = modelo.setData(
                modelo.index(0, Columna.FECHA_SALIDA), dt.date(2023, 1, 1)
            )

        assert resultado is False
        assert "01/01/2023" in señal.args[0]
        assert "10/01/2024" in señal.args[0]
        assert modelo.data(modelo.index(0, Columna.FECHA_ENTRADA)) == "10/01/2024"
        assert modelo.data(modelo.index(0, Columna.FECHA_SALIDA)) == ""

    def test_text_is_accepted_from_a_delegate_as_a_string(self, qtbot: object) -> None:
        dobles = PersistentDobleFactory()
        modelo = MovimientosTableModel(dobles.persistencia, usuario=USUARIO, filas=dobles.filas)
        assert modelo.setData(modelo.index(0, Columna.NOTA), "  revisar   fuente ")
        assert modelo.data(modelo.index(0, Columna.NOTA)) == "revisar fuente"

    def test_a_date_typed_as_text_is_parsed(self, qtbot: object) -> None:
        dobles = PersistentDobleFactory()
        modelo = MovimientosTableModel(dobles.persistencia, usuario=USUARIO, filas=dobles.filas)
        assert modelo.setData(modelo.index(0, Columna.FECHA_ENTRADA), "05/03/2024")
        assert modelo.data(modelo.index(0, Columna.FECHA_ENTRADA)) == "05/03/2024"

    def test_unparseable_text_raises_a_validation_error_signal(
        self, qtbot: object, modelo: MovimientosTableModel
    ) -> None:
        with qtbot.waitSignal(modelo.error_validacion, timeout=1000):  # type: ignore[attr-defined]
            assert modelo.setData(modelo.index(0, Columna.FECHA_ENTRADA), "31/02/2024") is False

    def test_the_model_requires_a_user(self, qtbot: object) -> None:
        with pytest.raises(ValueError, match="usuario"):
            MovimientosTableModel(PersistenciaFalsa(), usuario="  ")


class TestReemplazo:
    def test_replacing_the_contents_resets_the_model(self, modelo: MovimientosTableModel) -> None:
        modelo.reemplazar([fila(id=99)])
        assert modelo.rowCount() == 1
        assert modelo.fila(0).id == 99

    def test_locating_a_row_by_id(self, modelo: MovimientosTableModel) -> None:
        assert modelo.indice_de(2) == 1
        assert modelo.indice_de(12345) is None


class TestFiltro:
    def _proxy(self, qtbot: object) -> FiltroMovimientos:
        dobles = PersistentDobleFactory()
        modelo = MovimientosTableModel(dobles.persistencia, usuario=USUARIO, filas=dobles.filas)
        proxy = FiltroMovimientos()
        proxy.setSourceModel(modelo)
        return proxy

    def test_search_ignores_accents_and_case(self, qtbot: object) -> None:
        proxy = self._proxy(qtbot)
        proxy.set_texto("AGROMETEOROLOGIA")
        assert proxy.rowCount() == 1

    def test_search_requires_every_token(self, qtbot: object) -> None:
        filas = [
            fila(id=1, modelo="Dell Optiplex 3050", codigo_inventario="776"),
            fila(id=2, modelo="Dell Vostro 260", codigo_inventario="1251"),
        ]
        proxy = FiltroMovimientos()
        proxy.setSourceModel(
            MovimientosTableModel(PersistenciaFalsa(), usuario=USUARIO, filas=filas)
        )
        proxy.set_texto("dell 776")
        assert proxy.rowCount() == 1
        proxy.set_texto("dell 1251")
        assert proxy.rowCount() == 1
        proxy.set_texto("dell 9999")
        assert proxy.rowCount() == 0

    def test_search_looks_inside_technician_names(self, qtbot: object) -> None:
        filas = [
            fila(id=1, soporte=["Herrera"]),
            fila(id=2, soporte=["Carlos"]),
        ]
        proxy = FiltroMovimientos()
        proxy.setSourceModel(
            MovimientosTableModel(PersistenciaFalsa(), usuario=USUARIO, filas=filas)
        )
        proxy.set_texto("herrera")
        assert proxy.rowCount() == 1

    def test_filter_by_state(self, qtbot: object) -> None:
        proxy = self._proxy(qtbot)
        proxy.set_estado("despachado")
        assert proxy.rowCount() == 1
        proxy.set_estado(None)
        assert proxy.rowCount() == 3

    def test_filter_by_pending_review(self, qtbot: object) -> None:
        proxy = self._proxy(qtbot)
        proxy.set_solo_revision(True)
        assert proxy.rowCount() == 1

    def test_filters_combine(self, qtbot: object) -> None:
        proxy = self._proxy(qtbot)
        proxy.set_solo_revision(True)
        proxy.set_estado("despachado")
        assert proxy.rowCount() == 0

    def test_dates_sort_chronologically_not_lexicographically(self, qtbot: object) -> None:
        filas = [
            fila(id=1, fecha_entrada=dt.date(2024, 2, 1)),
            fila(id=2, fecha_entrada=dt.date(2023, 12, 31)),
        ]
        modelo = MovimientosTableModel(PersistenciaFalsa(), usuario=USUARIO, filas=filas)
        proxy = FiltroMovimientos()
        proxy.setSourceModel(modelo)
        proxy.sort(Columna.FECHA_ENTRADA, Qt.SortOrder.AscendingOrder)
        assert proxy.data(proxy.index(0, 0), Qt.ItemDataRole.UserRole) == "en_taller"
        primera = proxy.data(proxy.index(0, Columna.FECHA_ENTRADA))
        assert primera == "31/12/2023"

    def test_rows_without_dates_sort_last(self, qtbot: object) -> None:
        proxy = self._proxy(qtbot)
        proxy.sort(Columna.FECHA_ENTRADA, Qt.SortOrder.AscendingOrder)
        ultima = proxy.data(proxy.index(proxy.rowCount() - 1, Columna.FECHA_ENTRADA))
        assert ultima == ""

    def test_the_pure_helper_and_the_proxy_agree(self, qtbot: object) -> None:
        proxy = self._proxy(qtbot)
        proxy.set_texto("dell")
        filas = [proxy.data(proxy.index(n, Columna.MODELO)) for n in range(proxy.rowCount())]
        esperadas = filtrar(proxy.sourceModel().filas(), texto="dell")  # type: ignore[attr-defined]
        assert len(filas) == len(esperadas)


class TestDelegates:
    def test_the_right_delegate_is_chosen_per_column(self, qtbot: object) -> None:
        esperados: dict[Columna, type[object]] = {
            Columna.ESTADO: SemaforoDelegate,
            Columna.AREA: ComboDelegate,
            Columna.TIPO: ComboDelegate,
            Columna.FECHA_ENTRADA: FechaDelegate,
            Columna.FECHA_SALIDA: FechaDelegate,
        }
        for columna in Columna:
            delegado = delegate_por_columna(columna, areas=lambda: [], tipos=lambda: [])
            if columna in esperados:
                assert isinstance(delegado, esperados[columna]), columna
            else:
                assert delegado is None, columna

    def test_the_state_delegate_paints_the_expected_colour(self, qtbot: object) -> None:
        modelo = MovimientosTableModel(
            PersistenciaFalsa(), usuario=USUARIO, filas=[fila(estado="despachado")]
        )
        delegado = SemaforoDelegate()

        pixmap = QPixmap(40, 24)
        pixmap.fill(Qt.GlobalColor.white)
        pintor = QPainter(pixmap)
        opcion = QStyleOptionViewItem()
        opcion.rect = QRect(0, 0, 40, 24)
        opcion.widget = None
        delegado.paint(pintor, opcion, modelo.index(0, Columna.ESTADO))
        pintor.end()

        # Qt reports colour names in lower case; the constant is upper case.
        pintado = pixmap.toImage().pixelColor(20, 12).name().lower()
        assert pintado == COLOR_ESTADO["despachado"].lower()


class TestFechaDelegate:
    def _indice(self, valor: dt.date | None) -> object:
        class Indice:
            def data(self, rol: int) -> object:
                return valor if rol == Qt.ItemDataRole.UserRole else None

        return Indice()

    def test_the_editor_is_a_calendar_in_dd_mm_aaaa(self, qtbot: object) -> None:
        editor = FechaDelegate().createEditor(None, None, self._indice(None))  # type: ignore[arg-type]
        assert isinstance(editor, QDateEdit)
        assert editor.displayFormat() == "dd/MM/yyyy"
        assert editor.calendarPopup() is True

    def test_an_empty_date_shows_the_dash(self, qtbot: object) -> None:
        editor = FechaDelegate().createEditor(None, None, self._indice(None))  # type: ignore[arg-type]
        FechaDelegate().setEditorData(editor, self._indice(None))  # type: ignore[arg-type]
        assert editor.date() == FECHA_VACIA  # type: ignore[attr-defined]

    def test_an_existing_date_is_loaded(self, qtbot: object) -> None:
        editor = FechaDelegate().createEditor(None, None, self._indice(None))  # type: ignore[arg-type]
        FechaDelegate().setEditorData(editor, self._indice(dt.date(2024, 3, 5)))  # type: ignore[arg-type]
        assert editor.date() == QDate(2024, 3, 5)  # type: ignore[attr-defined]

    def test_the_empty_value_is_written_as_none(self, qtbot: object) -> None:
        escrituras: list[object] = []

        class Modelo:
            def setData(self, indice: object, valor: object, rol: int) -> None:  # noqa: N802
                escrituras.append(valor)

        editor = FechaDelegate().createEditor(None, None, self._indice(None))  # type: ignore[arg-type]
        editor.setDate(FECHA_VACIA)  # type: ignore[attr-defined]
        FechaDelegate().setModelData(editor, Modelo(), None)  # type: ignore[arg-type]
        assert escrituras == [None]


class TestComboDelegate:
    CATALOGO = [CatalogoLeido(id=3, nombre="Contabilidad"), CatalogoLeido(id=7, nombre="Prensa")]

    def test_the_editor_offers_the_catalog_plus_an_empty_option(self, qtbot: object) -> None:
        delegado = ComboDelegate(lambda: self.CATALOGO, permite_vacio=True)
        combo = delegado.createEditor(None, None, None)  # type: ignore[arg-type]
        assert isinstance(combo, QComboBox)
        assert combo.count() == 3
        assert combo.itemText(0) == "(sin asignar)"

    def test_the_current_value_is_selected(self, qtbot: object) -> None:
        class Indice:
            def data(self, rol: int) -> object:
                return 7 if rol == Qt.ItemDataRole.UserRole else None

        delegado = ComboDelegate(lambda: self.CATALOGO)
        combo = delegado.createEditor(None, None, Indice())  # type: ignore[arg-type]
        delegado.setEditorData(combo, Indice())  # type: ignore[arg-type]
        assert combo.currentData() == 7

    def test_the_identifier_is_written_not_the_name(self, qtbot: object) -> None:
        escrituras: list[object] = []

        class Modelo:
            def setData(self, indice: object, valor: object, rol: int) -> None:  # noqa: N802
                escrituras.append(valor)

        delegado = ComboDelegate(lambda: self.CATALOGO)
        combo = delegado.createEditor(None, None, None)  # type: ignore[arg-type]
        combo.setCurrentIndex(1)
        delegado.setModelData(combo, Modelo(), None)  # type: ignore[arg-type]
        assert escrituras == [7]
