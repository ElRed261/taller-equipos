"""Ventana de edición de un movimiento.

El doble clic en el grid ya no edita la celda: abre esta ventana. Editar una celda
suelta dentro de una tabla es rápido pero opaco — no ves el registro completo, no
ves qué más estás por cambiar, y un clic mal dado modifica producción sin que nadie
lo note.

Acá se ve todo el registro, se cambia lo que haga falta y se guarda una sola vez.
"""

from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from taller.inventario import normalizar_codigo
from taller.schemas.movimiento import (
    CatalogoLeido,
    FechasInvalidas,
    MovimientoActualizar,
    MovimientoLeido,
)
from taller.servicios import ServicioTaller
from taller.ui.iconos import icono
from taller.ui.tema import COLORES, ETIQUETA_ESTADO, estilo_badge_estado

ANIO_MINIMO = 1990
FECHA_VACIA = QDate(ANIO_MINIMO, 1, 1)
SIN_FECHA = "—"


class MovimientoDialog(QDialog):
    """Editar un movimiento completo. Devuelve el DTO actualizado al aceptar."""

    def __init__(
        self,
        servicio: ServicioTaller,
        movimiento: MovimientoLeido,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._servicio = servicio
        self._movimiento = movimiento
        self.actualizado: MovimientoLeido | None = None

        self.setWindowTitle("Editar movimiento")
        self.setMinimumSize(780, 660)
        self._construir()
        self._cargar()

    # ------------------------------------------------------------------ armado

    def _construir(self) -> None:
        badge = QLabel(f"● {ETIQUETA_ESTADO[self._movimiento.estado]}")
        badge.setStyleSheet(estilo_badge_estado(self._movimiento.estado))
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        referencia = QLabel(self._referencia())
        referencia.setObjectName("SubtituloVista")

        encabezado = QHBoxLayout()
        encabezado.setSpacing(12)
        encabezado.addWidget(badge)
        encabezado.addWidget(referencia, 1)

        self.area = QComboBox()
        self.tipo = QComboBox()
        self.modelo = QLineEdit()
        self.inventario = QLineEdit()
        self.inventario.setToolTip("Se completa a cinco dígitos: 1716 queda 01716")
        self.service_tag = QLineEdit()

        self.fecha_entrada = QDateEdit()
        self.fecha_entrada.setCalendarPopup(True)
        self.fecha_entrada.setDisplayFormat("dd/MM/yyyy")
        self.fecha_entrada.setMinimumDate(QDate(ANIO_MINIMO, 1, 1))

        self.fecha_salida = QDateEdit()
        self.fecha_salida.setCalendarPopup(True)
        self.fecha_salida.setDisplayFormat("dd/MM/yyyy")
        self.fecha_salida.setMinimumDate(FECHA_VACIA)
        self.fecha_salida.setSpecialValueText(SIN_FECHA)

        self.diagnostico = QLineEdit()
        self.diagnostico.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.nota = QPlainTextEdit()
        self.nota.setFrameShape(QFrame.Shape.NoFrame)
        self.nota.setFixedHeight(100)
        self.nota.setTabChangesFocus(True)

        self._contenedor_soportes = QWidget()
        self._contenedor_soportes.setObjectName("Contenedor")
        self._grilla_soportes = QGridLayout(self._contenedor_soportes)
        self._grilla_soportes.setContentsMargins(0, 0, 0, 0)
        self._grilla_soportes.setHorizontalSpacing(8)
        self._grilla_soportes.setVerticalSpacing(8)
        self._chips: dict[int, QPushButton] = {}

        self.error = QLabel()
        self.error.setObjectName("ErrorValidacion")
        self.error.setWordWrap(True)
        self.error.hide()

        grilla = QGridLayout()
        grilla.setHorizontalSpacing(20)
        grilla.setVerticalSpacing(12)
        grilla.addWidget(self._campo("Área", self.area), 0, 0)
        grilla.addWidget(self._campo("Equipo", self.tipo), 0, 1)
        grilla.addWidget(self._campo("Modelo", self.modelo), 1, 0)
        grilla.addWidget(self._campo("Inventario", self.inventario), 1, 1)
        grilla.addWidget(self._campo("Service Tag", self.service_tag), 2, 0)
        grilla.addWidget(self._grupo_fechas(), 2, 1)
        grilla.addWidget(
            self._campo("Diagnóstico", self.diagnostico), 3, 0, Qt.AlignmentFlag.AlignTop
        )
        grilla.addWidget(self._campo("Nota", self.nota), 3, 1)
        grilla.addWidget(self._grupo_soportes(), 4, 0, 1, 2)
        grilla.setColumnStretch(0, 1)
        grilla.setColumnStretch(1, 1)

        contenido = QWidget()
        contenido.setObjectName("Contenedor")
        columna = QVBoxLayout(contenido)
        columna.setContentsMargins(20, 18, 20, 12)
        columna.setSpacing(12)
        columna.addLayout(encabezado)
        divisor = QFrame()
        divisor.setObjectName("Divisor")
        divisor.setFixedHeight(1)
        columna.addWidget(divisor)
        columna.addLayout(grilla)
        columna.addWidget(self.error)

        area_scroll = QScrollArea()
        area_scroll.setWidget(contenido)
        area_scroll.setWidgetResizable(True)
        area_scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        botones = QDialogButtonBox()
        guardar = QPushButton("Guardar cambios")
        guardar.setObjectName("BotonPrimario")
        guardar.setIcon(icono("guardar", COLORES["blanco"]))
        cancelar = QPushButton("Cancelar")
        botones.addButton(guardar, QDialogButtonBox.ButtonRole.AcceptRole)
        botones.addButton(cancelar, QDialogButtonBox.ButtonRole.RejectRole)
        guardar.clicked.connect(self.guardar)
        cancelar.clicked.connect(self.reject)

        caja = QVBoxLayout(self)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(0)
        caja.addWidget(area_scroll, 1)
        pie = QWidget()
        pie_columna = QHBoxLayout(pie)
        pie_columna.setContentsMargins(20, 10, 20, 14)
        pie_columna.addStretch(1)
        pie_columna.addWidget(botones)
        caja.addWidget(pie)

    @staticmethod
    def _campo(etiqueta: str, control: QWidget) -> QWidget:
        caja = QWidget()
        caja.setObjectName("Contenedor")
        columna = QVBoxLayout(caja)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(5)
        texto = QLabel(etiqueta)
        texto.setObjectName("EtiquetaCampo")
        columna.addWidget(texto)
        columna.addWidget(control)
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
        texto = QLabel("Soportes que intervinieron")
        texto.setObjectName("EtiquetaCampo")
        columna.addWidget(texto)
        columna.addWidget(self._contenedor_soportes)
        return caja

    def _referencia(self) -> str:
        partes = []
        if self._movimiento.legacy_linea is not None:
            partes.append(f"línea {self._movimiento.legacy_linea} del archivo original")
        if self._movimiento.fecha_entrada_inferida:
            partes.append("fecha de entrada inferida")
        if self._movimiento.requiere_revision:
            partes.append("marcado para revisión")
        return " · ".join(partes) or "registro creado desde la aplicación"

    # ------------------------------------------------------------------ datos

    def _cargar(self) -> None:
        self._cargar_combo(self.area, self._servicio.areas(), self._movimiento.area_id)
        self._cargar_combo(
            self.tipo, self._servicio.tipos_equipo(), self._movimiento.tipo_equipo_id
        )
        self.modelo.setText(self._movimiento.modelo or "")
        self.inventario.setText(self._movimiento.codigo_inventario or "")
        self.service_tag.setText(self._movimiento.service_tag or "")
        self.fecha_entrada.setDate(
            _a_qdate(self._movimiento.fecha_entrada) or QDate.currentDate()
        )
        self.fecha_salida.setDate(_a_qdate(self._movimiento.fecha_salida) or FECHA_VACIA)
        self.diagnostico.setText(self._movimiento.diagnostico or "")
        self.nota.setPlainText(self._movimiento.nota or "")
        self._cargar_soportes()

    @staticmethod
    def _cargar_combo(combo: QComboBox, filas: list[CatalogoLeido], actual: int | None) -> None:
        combo.clear()
        combo.addItem("(sin asignar)", None)
        for fila in filas:
            combo.addItem(fila.nombre, fila.id)
        posicion = combo.findData(actual)
        combo.setCurrentIndex(max(posicion, 0))

    def _cargar_soportes(self) -> None:
        marcados = set(self._movimiento.soporte)
        filas = self._servicio.tecnicos()
        for indice, fila in enumerate(filas):
            chip = QPushButton(fila.nombre)
            chip.setObjectName("ChipSoporte")
            chip.setCheckable(True)
            chip.setChecked(fila.nombre in marcados)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            self._grilla_soportes.addWidget(chip, indice // 5, indice % 5)
            self._chips[fila.id] = chip
        self._contenedor_soportes.setMinimumHeight(max(1, -(-len(filas) // 5)) * 35)

    def _tecnicos_marcados(self) -> list[int]:
        return [identificador for identificador, chip in self._chips.items() if chip.isChecked()]

    def cambios(self) -> MovimientoActualizar:
        """Lo que el usuario cambió, listo para el repositorio."""
        salida = self.fecha_salida.date()
        return MovimientoActualizar(
            fecha_entrada=self.fecha_entrada.date().toPython(),
            fecha_salida=None if salida == FECHA_VACIA else salida.toPython(),
            area_id=self.area.currentData(),
            tipo_equipo_id=self.tipo.currentData(),
            modelo=self.modelo.text() or None,
            codigo_inventario=normalizar_codigo(self.inventario.text() or None),
            service_tag=self.service_tag.text() or None,
            diagnostico=self.diagnostico.text() or None,
            nota=self.nota.toPlainText() or None,
            tecnicos=self._tecnicos_marcados(),
        )

    # ------------------------------------------------------------------ guardar

    def guardar(self) -> MovimientoLeido | None:
        try:
            self.actualizado = self._servicio.actualizar(self._movimiento.id, self.cambios())
        except (FechasInvalidas, ValueError) as exc:
            self.error.setText(str(exc))
            self.error.show()
            return None
        self.accept()
        return self.actualizado


def _a_qdate(fecha: object) -> QDate | None:
    if fecha is None or not hasattr(fecha, "year"):
        return None
    return QDate(fecha.year, fecha.month, fecha.day)  # type: ignore[attr-defined]
