"""Entrada de equipo: la pantalla casa de la aplicación.

Decisión de producto: el formulario es la casa, no una ventana secundaria. Un
técnico pasa la mayor parte del tiempo cargando equipos.

Solo ocho campos (2026-10-30): fecha de entrada, fecha de salida, área, equipo,
modelo, inventario, service tag y soportes. El diagnóstico y la nota no se cargan
acá: se leen y se editan en el panel de detalle del grid, que es donde hacen
falta. Un formulario corto se termina rápido y se vuelve a usar.

Dos detalles que existen para que no vuelva la basura del CSV original:

* Área, Equipo y Soportes se eligen del catálogo. Si el técnico tipea un área que
  no existe, se crea en el momento en vez de quedar como una variante nueva.
* La fecha de entrada tiene mínimo en 1990, que es la corrección del año ``1023``
  que traía el archivo legado.
"""

from __future__ import annotations

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from taller.schemas.movimiento import (
    CatalogoLeido,
    FechasInvalidas,
    MovimientoCrear,
    MovimientoLeido,
)
from taller.servicios import ServicioTaller
from taller.ui.iconos import icono
from taller.ui.tema import COLORES

ANIO_MINIMO = 1990
FECHA_VACIA = QDate(ANIO_MINIMO, 1, 1)
SIN_FECHA = "—"
COLUMNAS_SOPORTES = 4
#: La nota va al costado derecho, con forma de cuadrado.
ANCHO_NOTA = 260
ALTO_NOTA = 170


def _etiqueta(texto: str) -> QLabel:
    etiqueta = QLabel(texto)
    etiqueta.setObjectName("EtiquetaCampo")
    return etiqueta


def _divisor() -> QFrame:
    linea = QFrame()
    linea.setObjectName("Divisor")
    linea.setFixedHeight(1)
    linea.setFrameShape(QFrame.Shape.NoFrame)
    return linea


class FormRegistroView(QWidget):
    """Carga rápida por teclado. Ctrl+Enter guarda y deja el formulario listo."""

    movimiento_creado = Signal(object)
    error_validacion = Signal(str)

    def __init__(self, servicio: ServicioTaller, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._servicio = servicio
        self._chips_soporte: dict[int, QPushButton] = {}
        self._construir()
        self._cablear()
        self.refrescar_catalogos()
        self.limpiar()

    # ------------------------------------------------------------------ armado

    def _construir(self) -> None:
        tarjeta = QFrame()
        tarjeta.setObjectName("Tarjeta")

        titulo = QLabel("Entrada de equipo")
        titulo.setObjectName("TituloVista")
        subtitulo = QLabel(
            "Diez campos. Al guardar, el formulario queda listo para el siguiente equipo."
        )
        subtitulo.setObjectName("SubtituloVista")

        # Solo se elige de la lista: los catálogos se administran en Configuración.
        # Editable + botón «+» obligaba a adivinar si había que escribir o desplegar.
        self.area = self._combo("Elegí un área…")
        self.tipo = self._combo("Elegí un equipo…")
        self.modelo = QLineEdit()
        self.modelo.setPlaceholderText("Dell Optiplex 3050")
        self.inventario = QLineEdit()
        self.inventario.setPlaceholderText("776")
        self.service_tag = QLineEdit()
        self.service_tag.setPlaceholderText("opcional")

        # Diagnóstico de una línea, como los demás campos.
        self.diagnostico = QLineEdit()
        self.diagnostico.setPlaceholderText("Qué reporta el usuario y qué se observa")
        self.diagnostico.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        # La nota ocupa la altura de toda la columna derecha: arranca donde el
        # diagnóstico y termina donde los soportes, así su marco cierra con el
        # contenido de al lado en lugar de quedar flotando.
        self.nota = QPlainTextEdit()
        self.nota.setPlaceholderText("Aclaraciones, accesorios entregados, pendientes…")
        self.nota.setFrameShape(QFrame.Shape.NoFrame)
        self.nota.setTabChangesFocus(True)
        # Política vertical «Ignored»: el alto de la nota lo decide la columna de
        # al lado, no su tamaño preferido. Con «Expanding» el widget imponía su
        # sizeHint y quedaba más alto que el contenido izquierdo.
        self.nota.setFixedSize(ANCHO_NOTA, ALTO_NOTA)

        self.fecha_entrada = QDateEdit()
        self.fecha_entrada.setCalendarPopup(True)
        self.fecha_entrada.setDisplayFormat("dd/MM/yyyy")
        self.fecha_entrada.setMinimumDate(QDate(ANIO_MINIMO, 1, 1))

        self.fecha_salida = QDateEdit()
        self.fecha_salida.setCalendarPopup(True)
        self.fecha_salida.setDisplayFormat("dd/MM/yyyy")
        self.fecha_salida.setMinimumDate(FECHA_VACIA)
        self.fecha_salida.setSpecialValueText(SIN_FECHA)
        self.fecha_salida.setToolTip("Dejala en «—» si el equipo todavía está en el taller")

        self._contenedor_soportes = QWidget()
        self._contenedor_soportes.setObjectName("Contenedor")
        self._grilla_soportes = QGridLayout(self._contenedor_soportes)
        self._grilla_soportes.setContentsMargins(0, 0, 0, 0)
        self._grilla_soportes.setHorizontalSpacing(8)
        self._grilla_soportes.setVerticalSpacing(8)
        self._grilla_soportes.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.error = QLabel()
        self.error.setObjectName("ErrorValidacion")
        self.error.setWordWrap(True)
        self.error.hide()

        self.boton_registrar = QPushButton("Registrar entrada")
        self.boton_registrar.setObjectName("BotonPrimario")
        self.boton_registrar.setIcon(icono("guardar", COLORES["blanco"]))
        self.boton_limpiar = QPushButton("Limpiar")
        # --- dos columnas parejas; cada campo es etiqueta + control ---
        grilla = QGridLayout()
        grilla.setHorizontalSpacing(22)
        grilla.setVerticalSpacing(14)
        grilla.addWidget(self._campo("Área", self.area), 0, 0)
        grilla.addWidget(self._campo("Equipo", self.tipo), 0, 1)
        grilla.addWidget(self._campo("Modelo", self.modelo), 1, 0)
        grilla.addWidget(self._campo("Inventario", self.inventario), 1, 1)
        grilla.addWidget(self._campo("Service Tag", self.service_tag), 2, 0)
        grilla.addWidget(self._grupo_fechas(), 2, 1)
        # Bloque final: diagnóstico y soportes ocupan el ancho, y la nota queda
        # como un cuadrado al costado derecho. Compartir la grilla de dos
        # columnas la dejaba sin vecino de su altura; acá el bloque es una fila
        # propia y la nota se apoya en el borde derecho.
        columna_izquierda = QWidget()
        columna_izquierda.setObjectName("Contenedor")
        izquierda = QVBoxLayout(columna_izquierda)
        izquierda.setContentsMargins(0, 0, 0, 0)
        izquierda.setSpacing(14)
        izquierda.addWidget(self._campo("Diagnóstico", self.diagnostico))
        izquierda.addWidget(self._grupo_soportes())
        izquierda.addStretch(1)

        bloque_final = QHBoxLayout()
        bloque_final.setContentsMargins(0, 0, 0, 0)
        bloque_final.setSpacing(22)
        bloque_final.addWidget(columna_izquierda, 1)
        bloque_final.addWidget(
            self._campo("Nota", self.nota),
            0,
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
        )
        grilla.addLayout(bloque_final, 3, 0, 1, 2)
        grilla.setColumnStretch(0, 1)
        grilla.setColumnStretch(1, 1)

        acciones = QHBoxLayout()
        acciones.setSpacing(10)
        acciones.addWidget(self.boton_registrar)
        acciones.addWidget(self.boton_limpiar)
        acciones.addStretch(1)

        caja_tarjeta = QVBoxLayout(tarjeta)
        caja_tarjeta.setContentsMargins(28, 24, 28, 24)
        caja_tarjeta.setSpacing(6)
        caja_tarjeta.addWidget(titulo)
        caja_tarjeta.addWidget(subtitulo)
        caja_tarjeta.addSpacing(10)
        caja_tarjeta.addWidget(_divisor())
        caja_tarjeta.addSpacing(14)
        caja_tarjeta.addLayout(grilla)
        caja_tarjeta.addSpacing(8)
        caja_tarjeta.addWidget(self.error)
        caja_tarjeta.addSpacing(8)
        caja_tarjeta.addWidget(_divisor())
        caja_tarjeta.addSpacing(12)
        caja_tarjeta.addLayout(acciones)

        caja = QVBoxLayout(self)
        caja.setContentsMargins(26, 22, 26, 22)
        caja.addWidget(tarjeta, 0, Qt.AlignmentFlag.AlignTop)
        caja.addStretch(1)

    @staticmethod
    def _combo(marcador: str) -> QComboBox:
        """Desplegable cerrado con un primer ítem que dice qué elegir."""
        combo = QComboBox()
        combo.setEditable(False)
        combo.addItem(marcador, None)
        combo.setProperty("marcador", marcador)
        return combo

    @staticmethod
    def _campo(etiqueta: str, control: QWidget) -> QWidget:
        """Etiqueta arriba, control abajo: la misma forma para los ocho campos."""
        caja = QWidget()
        caja.setObjectName("Contenedor")
        columna = QVBoxLayout(caja)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(5)
        columna.addWidget(_etiqueta(etiqueta))
        if isinstance(control, QWidget):
            columna.addWidget(control)
        else:
            columna.addLayout(control)
        return caja

    def _grupo_fechas(self) -> QWidget:
        caja = QWidget()
        caja.setObjectName("Contenedor")
        fila = QHBoxLayout(caja)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(14)
        fila.addWidget(self._campo("Fecha de entrada", self.fecha_entrada), 1)
        fila.addWidget(self._campo("Fecha de salida", self.fecha_salida), 1)
        return caja

    def _grupo_soportes(self) -> QWidget:
        caja = QWidget()
        caja.setObjectName("Contenedor")
        columna = QVBoxLayout(caja)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(7)
        etiqueta = _etiqueta("Soportes que intervinieron")
        ayuda = QLabel("Se puede marcar más de uno.")
        ayuda.setObjectName("AyudaCampo")
        encabezado = QHBoxLayout()
        encabezado.setSpacing(8)
        encabezado.addWidget(etiqueta)
        encabezado.addWidget(ayuda)
        encabezado.addStretch(1)
        columna.addLayout(encabezado)
        columna.addWidget(self._contenedor_soportes)
        return caja

    @staticmethod
    def _con_boton(control: QWidget, boton: QWidget) -> QWidget:
        caja = QWidget()
        caja.setObjectName("Contenedor")
        fila = QHBoxLayout(caja)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(6)
        fila.addWidget(control, 1)
        fila.addWidget(boton)
        return caja

    def _cablear(self) -> None:
        self.boton_registrar.clicked.connect(self.registrar)
        self.boton_limpiar.clicked.connect(self.limpiar)
        QShortcut(QKeySequence("Ctrl+Return"), self).activated.connect(self.registrar)
        QShortcut(QKeySequence("Ctrl+Enter"), self).activated.connect(self.registrar)

    # --------------------------------------------------------------- catálogos

    def refrescar_catalogos(self) -> None:
        self._cargar_combo(self.area, self._servicio.areas())
        self._cargar_combo(self.tipo, self._servicio.tipos_equipo())
        self._cargar_soportes(self._servicio.tecnicos())

        completer = QCompleter(self._servicio.modelos_sugeridos())
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.modelo.setCompleter(completer)

    def _cargar_combo(self, combo: QComboBox, filas: list[CatalogoLeido]) -> None:
        anterior = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(str(combo.property("marcador")), None)
        for fila in filas:
            combo.addItem(fila.nombre, fila.id)
        posicion = combo.findData(anterior)
        combo.setCurrentIndex(posicion if posicion >= 0 else 0)
        combo.blockSignals(False)

    def _cargar_soportes(self, filas: list[CatalogoLeido]) -> None:
        marcados = set(self.tecnicos_marcados())
        while self._grilla_soportes.count():
            elemento = self._grilla_soportes.takeAt(0)
            if elemento is not None and elemento.widget() is not None:
                elemento.widget().deleteLater()
        self._chips_soporte = {}
        for indice, fila in enumerate(filas):
            chip = QPushButton(fila.nombre)
            chip.setObjectName("ChipSoporte")
            chip.setCheckable(True)
            chip.setChecked(fila.id in marcados)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            self._grilla_soportes.addWidget(
                chip, indice // COLUMNAS_SOPORTES, indice % COLUMNAS_SOPORTES
            )
            self._chips_soporte[fila.id] = chip
        # Sin alto mínimo el contenedor se comprime a cero cuando la ventana es
        # baja y los soportes desaparecen de la vista.
        filas_necesarias = max(
            1, -(-len(filas) // COLUMNAS_SOPORTES)  # división hacia arriba
        )
        self._contenedor_soportes.setMinimumHeight(filas_necesarias * 35)

    # ------------------------------------------------------------------ estado

    def limpiar(self) -> None:
        for combo in (self.area, self.tipo):
            combo.setCurrentIndex(0)
        self.modelo.clear()
        self.inventario.clear()
        self.service_tag.clear()
        self.fecha_entrada.setDate(QDate.currentDate())
        self.fecha_salida.setDate(FECHA_VACIA)
        self.diagnostico.clear()
        self.nota.clear()
        for chip in self._chips_soporte.values():
            chip.setChecked(False)
        self.error.hide()
        self.area.setFocus()

    def tecnicos_marcados(self) -> list[int]:
        return [
            identificador
            for identificador, chip in self._chips_soporte.items()
            if chip.isChecked()
        ]

    def datos(self) -> MovimientoCrear:
        """Leer los widgets al esquema. Lanza ``ValueError`` si algo no cierra."""
        salida = self.fecha_salida.date()
        return MovimientoCrear(
            fecha_entrada=self.fecha_entrada.date().toPython(),
            fecha_salida=None if salida == FECHA_VACIA else salida.toPython(),
            area_id=self._resolver(self.area),
            tipo_equipo_id=self._resolver(self.tipo),
            modelo=self.modelo.text() or None,
            codigo_inventario=self.inventario.text() or None,
            service_tag=self.service_tag.text() or None,
            diagnostico=self.diagnostico.text() or None,
            nota=self.nota.toPlainText() or None,
            tecnicos=self.tecnicos_marcados(),
        )

    def _resolver(self, combo: QComboBox) -> int | None:
        """El id de la fila elegida del catálogo, o ``None`` si no se eligió nada."""
        actual = combo.currentData()
        return int(actual) if actual is not None else None

    # ------------------------------------------------------------------ guardar

    def registrar(self) -> MovimientoLeido | None:
        try:
            creado = self._servicio.crear_movimiento(self.datos())
        except (FechasInvalidas, ValueError) as exc:
            self.error.setText(str(exc))
            self.error.show()
            self.error_validacion.emit(str(exc))
            return None

        self.error.hide()
        self.movimiento_creado.emit(creado)
        self.limpiar()
        return creado
