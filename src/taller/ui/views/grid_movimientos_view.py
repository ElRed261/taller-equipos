"""Grid de movimientos: buscar, leer y actuar.

El panel de la derecha no es un adorno: el grid tiene doce columnas y a 1366 px
no entran todas. Ahí viven el diagnóstico completo, la nota y el historial de
auditoría, que en una celda no caben y en un tooltip no se pueden leer.

Las dos acciones del panel son las que evitan abrir el formulario:

* **Marcar salida hoy** cierra el ciclo de un equipo en un clic.
* **Marcar como revisado** se habilita recién cuando las fechas son consistentes,
  porque es la única forma de sacar la marca que saltea el CHECK de la base.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from taller.exportacion import escribir_csv, nombre_sugerido
from taller.schemas.movimiento import Estado, FechasInvalidas, MovimientoLeido
from taller.servicios import ServicioTaller
from taller.ui.delegates.grid_delegates import delegate_por_columna
from taller.ui.iconos import icono
from taller.ui.models.filtro_movimientos import FiltroMovimientos
from taller.ui.models.movimientos_table_model import (
    ETIQUETA_ESTADO,
    Columna,
    MovimientosTableModel,
)
from taller.ui.tema import COLORES, estilo_badge_estado
from taller.ui.views.movimiento_dialog import MovimientoDialog

#: (etiqueta, estado, es_revision)
CHIPS: tuple[tuple[str, Estado | None, bool], ...] = (
    ("Todos", None, False),
    ("En taller", "en_taller", False),
    ("Despachados", "despachado", False),
    ("Sin datos", "sin_datos", False),
    ("Requiere revisión", None, True),
)


class GridMovimientosView(QWidget):
    mensaje = Signal(str)
    error_validacion = Signal(str)

    def __init__(
        self, servicio: ServicioTaller, usuario: str, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._servicio = servicio
        self._usuario = usuario
        self._construir()
        self._cablear()
        self.recargar()

    # ------------------------------------------------------------------ armado

    def _construir(self) -> None:
        self.busqueda = QLineEdit()
        self.busqueda.setPlaceholderText(
            "Buscar por inventario, área, modelo, diagnóstico, técnico o nota…"
        )
        self.busqueda.setClearButtonEnabled(True)
        self.busqueda.addAction(
            icono("buscar", COLORES["gris-500"]),
            QLineEdit.ActionPosition.LeadingPosition,
        )

        self.chips: dict[str, QPushButton] = {}
        grupo = QButtonGroup(self)
        grupo.setExclusive(True)
        fila_chips = QHBoxLayout()
        fila_chips.setSpacing(6)
        for etiqueta, _estado, es_revision in CHIPS:
            chip = QPushButton(etiqueta)
            chip.setObjectName("ChipAviso" if es_revision else "Chip")
            chip.setCheckable(True)
            chip.setChecked(etiqueta == "Todos")
            grupo.addButton(chip)
            fila_chips.addWidget(chip)
            self.chips[etiqueta] = chip
        fila_chips.addStretch(1)
        self.boton_exportar = QPushButton("Exportar CSV")
        self.boton_exportar.setIcon(icono("exportar", COLORES["gris-700"]))
        self.boton_exportar.setToolTip(
            "Guarda lo que estás viendo, con los filtros aplicados"
        )
        fila_chips.addWidget(self.boton_exportar)
        self.boton_panel = QPushButton("Ocultar detalle")
        self.boton_panel.setObjectName("Chip")
        self.boton_panel.setIcon(icono("panel", COLORES["gris-700"]))
        self.boton_panel.setCheckable(True)
        self.boton_panel.setToolTip(
            "Plegar el panel de la derecha para leer la nota completa"
        )
        fila_chips.addWidget(self.boton_panel)
        self.visibles = QLabel()
        self.visibles.setStyleSheet(
            "color:#55606F;font-size:12px;padding-left:8px;background:transparent;"
        )
        fila_chips.addWidget(self.visibles)
        self._grupo_chips = grupo

        self._modelo = MovimientosTableModel(self._servicio, usuario=self._usuario)
        self._proxy = FiltroMovimientos()
        self._proxy.setSourceModel(self._modelo)

        self.tabla = QTableView()
        self.tabla.setModel(self._proxy)
        self.tabla.setSortingEnabled(True)
        # A propósito no se ordena al construir: el repositorio ya entrega el orden
        # de trabajo, con lo que necesita revisión al final. `sortByColumn(-1)` deja
        # la tabla en ese orden aunque la ordenación esté habilitada; si no, Qt
        # ordena sola por la primera columna y tira ese orden a la basura. Al tocar
        # un encabezado se ordena por esa columna, que es lo que se pidió al hacer
        # clic.
        self.tabla.sortByColumn(-1, Qt.SortOrder.AscendingOrder)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # Editar una celda suelta dentro de la tabla es rápido pero opaco: no ves
        # el registro completo ni qué más estás cambiando. El doble clic abre la
        # ventana de edición, que guarda todo de una vez y audita campo por campo.
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(26)
        cabecera = self.tabla.horizontalHeader()
        cabecera.setStretchLastSection(False)
        anchos = {
            Columna.ESTADO: 30,
            Columna.FECHA_ENTRADA: 100,
            Columna.FECHA_SALIDA: 100,
            Columna.AREA: 118,
            Columna.TIPO: 76,
            Columna.MODELO: 122,
            Columna.INVENTARIO: 80,
            Columna.SERVICE_TAG: 96,
            Columna.SOPORTE: 108,
            Columna.NOTA: 210,
            Columna.REVISION: 30,
        }
        for columna, ancho in anchos.items():
            self.tabla.setColumnWidth(int(columna), ancho)
        # Diagnóstico y Service Tag viven en el panel de detalle, que los muestra
        # completos. Ocultarlos acá es lo que le da ancho a Nota: con doce columnas
        # visibles la nota no entraba y las fechas se cortaban.
        # Tres columnas viven además en el panel de detalle, que las muestra
        # completas: ocultarlas acá es lo que le da a Nota un ancho legible.
        for oculta in (Columna.DIAGNOSTICO, Columna.SERVICE_TAG, Columna.SOPORTE):
            self.tabla.setColumnHidden(int(oculta), True)
        # Nota con ancho propio y arrastrable, no un resto que se encoge.
        cabecera.setSectionResizeMode(int(Columna.NOTA), QHeaderView.ResizeMode.Interactive)
        cabecera.setStretchLastSection(True)
        self.tabla.setTextElideMode(Qt.TextElideMode.ElideRight)

        self._instalar_delegates()

        panel = self._construir_panel()
        self._panel = panel

        centro = QHBoxLayout()
        centro.setSpacing(0)
        centro.addWidget(self.tabla, 1)
        centro.addWidget(panel)

        caja = QVBoxLayout(self)
        caja.setContentsMargins(16, 14, 0, 0)
        caja.setSpacing(10)
        caja.addWidget(self.busqueda)
        caja.addLayout(fila_chips)
        caja.addLayout(centro)

    def _instalar_delegates(self) -> None:
        # El semáforo se pinta; los editores en celda ya no se usan porque la
        # edición pasa por la ventana.
        self.tabla.setItemDelegateForColumn(
            int(Columna.ESTADO),
            delegate_por_columna(Columna.ESTADO, areas=lambda: [], tipos=lambda: []),
        )

    def _construir_panel(self) -> QWidget:
        """Panel de detalle por tarjetas.

        Antes era un bloque de texto corrido: toda la información pesaba lo mismo
        y no había dónde apoyar la vista. Ahora cada bloque tiene su título, su
        borde y su jerarquía, y el inventario va en monoespaciada porque es un
        código, no una frase.
        """
        panel = QWidget()
        panel.setObjectName("PanelDetalle")
        panel.setFixedWidth(302)

        self._badge = QLabel("Sin selección")
        self._badge.setObjectName("BadgeEstado")
        self._badge.setStyleSheet(
            "background:#EFF2F6;color:#55606F;border-radius:10px;"
            "padding:4px 11px;font-weight:700;font-size:12px;"
        )
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._valores: dict[str, QLabel] = {}
        self._tarjetas: list[QWidget] = []

        self._tarjeta("Fechas", [("Entrada", "fecha_entrada"), ("Salida", "fecha_salida")])
        self._tarjeta(
            "Equipo",
            [
                ("Área", "area"),
                ("Tipo", "tipo_equipo"),
                ("Modelo", "modelo"),
                ("Inventario", "inventario"),
                ("Service Tag", "service_tag"),
            ],
        )
        tarjeta_soportes = self._tarjeta("Soportes", [])
        self._soportes_valor = QLabel("—")
        self._soportes_valor.setObjectName("ValorDetalle")
        self._soportes_valor.setWordWrap(True)
        self._soportes_valor.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        tarjeta_soportes.layout().addWidget(self._soportes_valor)

        tarjeta_diagnostico = self._tarjeta("Diagnóstico", [])
        self._diagnostico_valor = QLabel("—")
        self._diagnostico_valor.setObjectName("ValorDetalle")
        self._diagnostico_valor.setWordWrap(True)
        self._diagnostico_valor.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        tarjeta_diagnostico.layout().addWidget(self._diagnostico_valor)

        tarjeta_nota = self._tarjeta("Nota", [])
        self._nota_valor = QLabel("—")
        self._nota_valor.setObjectName("ValorDetalle")
        self._nota_valor.setWordWrap(True)
        self._nota_valor.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        tarjeta_nota.layout().addWidget(self._nota_valor)

        self._aviso = QLabel()
        self._aviso.setObjectName("AvisoRevision")
        self._aviso.setWordWrap(True)
        self._aviso.hide()

        self.boton_editar = QPushButton("Editar registro…")
        self.boton_editar.setIcon(icono("editar", COLORES["azul-700"]))
        self.boton_editar.setEnabled(False)
        self.boton_salida = QPushButton("Marcar salida hoy")
        self.boton_salida.setIcon(icono("salida", COLORES["blanco"]))
        self.boton_salida.setObjectName("BotonPrimario")
        self.boton_salida.setEnabled(False)
        self.boton_revisado = QPushButton("Marcar como revisado")
        self.boton_revisado.setEnabled(False)

        contenido = QWidget()
        contenido.setObjectName("Contenedor")
        self._contenido_panel = contenido
        columna = QVBoxLayout(contenido)
        columna.setContentsMargins(14, 16, 14, 14)
        columna.setSpacing(10)
        columna.addWidget(self._badge)
        for tarjeta in self._tarjetas:
            columna.addWidget(tarjeta)
        columna.addWidget(self._aviso)
        columna.addStretch(1)
        columna.addWidget(self.boton_editar)
        columna.addWidget(self.boton_salida)
        columna.addWidget(self.boton_revisado)

        area = QScrollArea()
        area.setWidget(contenido)
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        caja = QVBoxLayout(panel)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.addWidget(area)
        return panel

    def _tarjeta(self, titulo: str, campos: list[tuple[str, str]]) -> QFrame:
        tarjeta = QFrame()
        tarjeta.setObjectName("TarjetaDetalle")
        columna = QVBoxLayout(tarjeta)
        columna.setContentsMargins(11, 9, 11, 10)
        columna.setSpacing(5)

        encabezado = QLabel(titulo.upper())
        encabezado.setObjectName("PanelTitulo")
        encabezado.setStyleSheet(
            "color:#6B7684;font-size:10px;font-weight:700;letter-spacing:.07em;"
            "background:transparent;"
        )
        columna.addWidget(encabezado)

        for clave, identificador in campos:
            fila = QHBoxLayout()
            fila.setContentsMargins(0, 0, 0, 0)
            fila.setSpacing(8)
            nombre = QLabel(clave)
            nombre.setObjectName("ClaveDetalle")
            nombre.setFixedWidth(74)
            valor = QLabel("—")
            valor.setObjectName(
                "ValorMono" if identificador in {"inventario", "service_tag"} else "ValorDetalle"
            )
            valor.setWordWrap(True)
            fila.addWidget(nombre)
            fila.addWidget(valor, 1)
            columna.addLayout(fila)
            self._valores[identificador] = valor

        self._tarjetas.append(tarjeta)
        return tarjeta

    def _cablear(self) -> None:
        self._temporizador = QTimer(self)
        self._temporizador.setSingleShot(True)
        self._temporizador.setInterval(250)
        self._temporizador.timeout.connect(self._aplicar_busqueda)

        self.busqueda.textChanged.connect(lambda _texto: self._temporizador.start())
        self._grupo_chips.buttonClicked.connect(lambda _boton: self._aplicar_chip())
        self.tabla.selectionModel().selectionChanged.connect(self._actualizar_panel)
        self._modelo.error_validacion.connect(self.error_validacion.emit)
        # clicked(bool) pasa el estado del botón como primer argumento: sin el
        # lambda, exportar_csv recibe False en lugar de la ruta.
        self.boton_editar.clicked.connect(self.editar_seleccionado)
        self.tabla.doubleClicked.connect(lambda _indice: self.editar_seleccionado())
        self.boton_exportar.clicked.connect(lambda _marcado=False: self.exportar_csv())
        self.boton_panel.toggled.connect(self._plegar_panel)
        self.boton_salida.clicked.connect(self.marcar_salida)
        self.boton_revisado.clicked.connect(self.marcar_revisado)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self.enfocar_busqueda)

    # ------------------------------------------------------------------ lectura

    def agregar(self, fila: MovimientoLeido) -> None:
        """Insert a row registered elsewhere (the form) without reloading."""
        self._modelo.insertar_fila(fila)
        self._actualizar_contadores()

    def recargar(self) -> None:
        filas = self._servicio.listar_movimientos()
        self._modelo.reemplazar(filas)
        self._actualizar_contadores()
        self._actualizar_visibles()
        self._actualizar_panel()

    def _actualizar_visibles(self) -> None:
        """Say how many rows the filters are letting through.

        The chip counters come from the database, so without this a technician
        who typed something in the search box sees "Requiere revisión · 14" over
        an empty table and concludes the data is gone.
        """
        visibles = self._proxy.rowCount()
        total = self._modelo.rowCount()
        if visibles == total:
            self.visibles.setText(f"{total} filas")
        else:
            self.visibles.setText(f"{visibles} de {total} filas")

    def _actualizar_contadores(self) -> None:
        resumen = self._servicio.resumen()
        cifras = {
            "Todos": resumen.total,
            "En taller": resumen.en_taller,
            "Despachados": resumen.despachado,
            "Sin datos": resumen.sin_datos,
            "Requiere revisión": resumen.pendientes_revision,
        }
        for etiqueta, chip in self.chips.items():
            chip.setText(f"{etiqueta} · {cifras.get(etiqueta, 0)}")

    def _aplicar_busqueda(self) -> None:
        self._proxy.set_texto(self.busqueda.text())
        self._actualizar_visibles()

    def _aplicar_chip(self) -> None:
        for etiqueta, estado, es_revision in CHIPS:
            if self.chips[etiqueta].isChecked():
                self._proxy.set_estado(estado)
                self._proxy.set_solo_revision(es_revision)
                self._actualizar_visibles()
                return

    def esta_filtrando_revision(self) -> bool:
        return self.chips["Requiere revisión"].isChecked()

    def _plegar_panel(self, plegado: bool) -> None:
        """Cerrar el panel devuelve ~300 px a la tabla.

        Es la alternativa honesta a recortar la columna Nota: el técnico decide
        si prefiere ver el detalle o leer la nota completa.
        """
        self._panel.setVisible(not plegado)
        self.boton_panel.setText("Mostrar detalle" if plegado else "Ocultar detalle")

    def filas_visibles(self) -> list[MovimientoLeido]:
        """Rows in the order the table shows them, with the filters applied."""
        salida: list[MovimientoLeido] = []
        for posicion in range(self._proxy.rowCount()):
            origen = self._proxy.mapToSource(self._proxy.index(posicion, 0))
            salida.append(self._modelo.fila(origen.row()))
        return salida

    def exportar_csv(self, ruta: Path | None = None) -> Path | None:
        """Write the visible rows to a CSV file.

        Only the grid offers this: the export is a snapshot of what the user is
        looking at, so it belongs where the filters live.
        """
        filas = self.filas_visibles()
        if not filas:
            self.error_validacion.emit("No hay filas para exportar con estos filtros.")
            return None

        if ruta is None:
            sugerido = nombre_sugerido(dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
            elegido, _filtro = QFileDialog.getSaveFileName(
                self, "Guardar como CSV", sugerido, "Archivos CSV (*.csv)"
            )
            if not elegido:
                return None
            ruta = Path(elegido)

        try:
            cantidad = escribir_csv(ruta, filas)
        except OSError as exc:
            self.error_validacion.emit(f"No se pudo escribir el archivo: {exc}")
            return None

        plural = "movimiento" if cantidad == 1 else "movimientos"
        self.mensaje.emit(f"{cantidad} {plural} exportados a {ruta.name}")
        return ruta

    def enfocar_busqueda(self) -> None:
        self.busqueda.setFocus()
        self.busqueda.selectAll()

    def mostrar_solo_revision(self) -> None:
        self.chips["Requiere revisión"].setChecked(True)
        self._aplicar_chip()

    def mostrar_todos(self) -> None:
        self.chips["Todos"].setChecked(True)
        self._aplicar_chip()

    # -------------------------------------------------------------------- panel

    def fila_seleccionada(self) -> MovimientoLeido | None:
        indices = self.tabla.selectionModel().selectedRows()
        if not indices:
            return None
        fuente = self._proxy.mapToSource(indices[0])
        return self._modelo.fila(fuente.row())

    def _actualizar_panel(self, *_args: object) -> None:
        fila = self.fila_seleccionada()
        if fila is None:
            self._badge.setText("Sin selección")
            self._badge.setStyleSheet(
                "background:#EFF2F6;color:#55606F;border-radius:10px;"
                "padding:4px 11px;font-weight:700;font-size:12px;"
            )
            for valor in self._valores.values():
                valor.setText("—")
            self._soportes_valor.setText("—")
            self._diagnostico_valor.setText("—")
            self._nota_valor.setText("—")
            self._aviso.hide()
            self.boton_salida.setEnabled(False)
            self.boton_revisado.setEnabled(False)
            self.boton_editar.setEnabled(False)
            return

        self._badge.setText(f"● {ETIQUETA_ESTADO[fila.estado]}")
        self._badge.setStyleSheet(estilo_badge_estado(fila.estado))

        self._valores["fecha_entrada"].setText(fila.fecha_entrada_texto or "—")
        self._valores["fecha_salida"].setText(fila.fecha_salida_texto or "—")
        self._valores["area"].setText(fila.area or "—")
        self._valores["tipo_equipo"].setText(fila.tipo_equipo or "—")
        self._valores["modelo"].setText(fila.modelo or "—")
        self._valores["inventario"].setText(fila.codigo_inventario or "—")
        self._valores["service_tag"].setText(fila.service_tag or "—")
        self._soportes_valor.setText(", ".join(fila.soporte) or "Sin soporte registrado")
        self._diagnostico_valor.setText(fila.diagnostico or "Sin diagnóstico registrado")
        self._nota_valor.setText(fila.nota or "Sin nota")

        if fila.requiere_revision:
            motivo = "Marcado durante la migración."
            if fila.fecha_entrada_inferida:
                motivo += " La fecha de entrada fue inferida por vecindad."
            self._aviso.setText(motivo)
            self._aviso.show()
        else:
            self._aviso.hide()

        self.boton_editar.setEnabled(True)
        self.boton_salida.setEnabled(fila.estado != "despachado")
        self.boton_revisado.setEnabled(puede_revisarse(fila))
        # Sin esto el texto envuelto se dibuja más alto que su tarjeta.
        self._contenido_panel.adjustSize()

    # ------------------------------------------------------------------ acciones

    def editar_seleccionado(self) -> MovimientoLeido | None:
        """Open the edit window for the selected row."""
        fila = self.fila_seleccionada()
        if fila is None:
            return None
        dialogo = MovimientoDialog(self._servicio, fila, self)
        if dialogo.exec() != QDialog.DialogCode.Accepted or dialogo.actualizado is None:
            return None
        actualizada = dialogo.actualizado
        self._modelo.actualizar_fila(actualizada)
        self._actualizar_contadores()
        self._actualizar_visibles()
        self._actualizar_panel()
        referencia = actualizada.modelo or actualizada.codigo_inventario or "el equipo"
        self.mensaje.emit(f"Registro de «{referencia}» actualizado")
        return actualizada

    def marcar_salida(self) -> None:
        fila = self.fila_seleccionada()
        if fila is None:
            return
        hoy = dt.date.today()
        respuesta = QMessageBox.question(
            self,
            "Marcar salida",
            f"¿Registrar la salida de «{fila.modelo or fila.codigo_inventario or 'el equipo'}» "
            f"hoy {hoy:%d/%m/%Y}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if respuesta != QMessageBox.StandardButton.Yes:
            return
        try:
            actualizada = self._servicio.marcar_salida(fila.id, hoy)
        except FechasInvalidas as exc:
            self.error_validacion.emit(str(exc))
            return
        self._modelo.actualizar_fila(actualizada)
        self._actualizar_contadores()
        self._actualizar_panel()
        self.mensaje.emit(f"Salida registrada el {hoy:%d/%m/%Y}")

    def marcar_revisado(self) -> None:
        fila = self.fila_seleccionada()
        if fila is None:
            return
        try:
            revisada = self._servicio.marcar_revisado(fila.id)
        except FechasInvalidas as exc:
            self.error_validacion.emit(str(exc))
            return
        self._modelo.actualizar_fila(revisada)
        self._actualizar_contadores()
        self._actualizar_panel()
        self.mensaje.emit("Registro marcado como revisado")


def _fechas_consistentes(fila: MovimientoLeido) -> bool:
    """The same rule the database enforces, used to enable the button."""
    if fila.fecha_entrada is None or fila.fecha_salida is None:
        return True
    return fila.fecha_salida >= fila.fecha_entrada


def puede_revisarse(fila: MovimientoLeido) -> bool:
    """Only flagged rows that actually have something to review.

    A row with no intake date stays flagged: there is nothing to confirm until
    someone records when the equipment arrived.
    """
    return (
        fila.requiere_revision
        and fila.fecha_entrada is not None
        and _fechas_consistentes(fila)
    )


__all__ = ["CHIPS", "GridMovimientosView"]
