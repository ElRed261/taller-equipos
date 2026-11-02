"""Ventana única con rail de navegación.

Tres secciones y ningún diálogo huérfano:

* **Registrar entrada** — la casa, por decisión de producto.
* **Movimientos** — el grid completo con buscador y panel de detalle.
* **Revisión** — el mismo grid, ya filtrado por las filas marcadas.

Registrar no cambia de página: el formulario se limpia y queda listo para el
siguiente equipo, y el grid recibe la fila nueva en memoria para que esté ahí
cuando el técnico vaya a consultar.
"""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from taller.arranque import ingreso_obligatorio
from taller.database.connection import reset_engine
from taller.schemas.movimiento import MovimientoLeido
from taller.servicios import ServicioTaller
from taller.ui.iconos import icono
from taller.ui.marca import cargar_marca
from taller.ui.tema import COLORES, cargar_logo
from taller.ui.views.configuracion_view import ConfiguracionView
from taller.ui.views.form_registro_view import FormRegistroView
from taller.ui.views.grid_movimientos_view import GridMovimientosView

#: Three sections, three pages. "Revisión" is no longer a section: it survives
#: as a chip inside Movimientos, which is where those rows are actually worked on.
SECCION_REGISTRAR = 0
SECCION_MOVIMIENTOS = 1
SECCION_CONFIGURACION = 2

PAGINA_FORMULARIO = 0
PAGINA_GRID = 1
PAGINA_CONFIGURACION = 2


class VentanaPrincipal(QMainWindow):
    def __init__(self, servicio: ServicioTaller, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._servicio = servicio
        self._marca = cargar_marca()
        self.setWindowTitle(self._marca.titulo_ventana)
        # El icono se fija también acá: una ventana abierta desde un script o
        # un test no pasa por main() y quedaba sin icono.
        self.setWindowIcon(QIcon(str(cargar_marca().logo)))
        self.resize(1280, 800)
        self.setMinimumSize(980, 640)

        self.formulario = FormRegistroView(servicio)
        self.grid = GridMovimientosView(servicio, servicio.usuario)
        self.configuracion = ConfiguracionView(servicio)

        self._paginas = QStackedWidget()
        self._paginas.addWidget(self.formulario)
        self._paginas.addWidget(self.grid)
        self._paginas.addWidget(self.configuracion)

        self._rail: dict[int, QPushButton] = {}
        rail = self._construir_rail()
        cuerpo = QWidget()
        fila = QHBoxLayout(cuerpo)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(0)
        fila.addWidget(rail)
        fila.addWidget(self._paginas, 1)

        contenedor = QWidget()
        columna = QVBoxLayout(contenedor)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(0)
        columna.addWidget(self._construir_barra())
        columna.addWidget(cuerpo, 1)
        self.setCentralWidget(contenedor)

        self._construir_estado()
        self._cablear()
        self.ir_a(PAGINA_FORMULARIO)

    # ------------------------------------------------------------------ armado

    def _construir_barra(self) -> QWidget:
        """Barra blanca con el logo institucional.

        La barra es blanca a propósito: el logo es azul marino sobre fondo blanco,
        así que sobre una barra azul aparecería como un parche. Acá se funde.
        """
        barra = QWidget()
        barra.setObjectName("BarraSuperior")
        barra.setFixedHeight(60)

        logo = QLabel()
        logo.setPixmap(cargar_logo(38))
        logo.setFixedWidth(42)
        logo.setToolTip(self._marca.nombre)

        sistema = QLabel(self._marca.nombre)
        sistema.setObjectName("BarraSistema")
        separador = QLabel("·")
        separador.setStyleSheet("color:#C7CFDA;background:transparent;")
        registro = QLabel(self._marca.descripcion)
        registro.setStyleSheet("color:#6B7684;font-size:12px;background:transparent;")

        self._conexion = QLabel("● conectado")
        self._conexion.setObjectName("BarraConexion")

        caja = QHBoxLayout(barra)
        caja.setContentsMargins(20, 0, 20, 0)
        caja.setSpacing(12)
        caja.addWidget(logo)
        caja.addWidget(sistema)
        caja.addWidget(separador)
        caja.addWidget(registro)
        caja.addStretch(1)
        caja.addWidget(self._conexion)
        return barra

    def _construir_rail(self) -> QWidget:
        rail = QWidget()
        rail.setObjectName("Rail")
        rail.setFixedWidth(212)

        grupo = QButtonGroup(self)
        grupo.setExclusive(True)
        caja = QVBoxLayout(rail)
        caja.setContentsMargins(0, 12, 0, 12)
        caja.setSpacing(2)

        for seccion, etiqueta, nombre_icono in (
            (SECCION_REGISTRAR, "Registrar entrada", "registrar"),
            (SECCION_MOVIMIENTOS, "Movimientos", "lista"),
            (SECCION_CONFIGURACION, "Configuración", "ajustes"),
        ):
            boton = QPushButton(etiqueta)
            boton.setIcon(icono(nombre_icono, COLORES["blanco"]))
            boton.setIconSize(QSize(17, 17))
            boton.setCheckable(True)
            grupo.addButton(boton)
            caja.addWidget(boton)
            self._rail[seccion] = boton
            boton.clicked.connect(lambda _c=False, destino=seccion: self.ir_a(destino))

        caja.addStretch(1)
        return rail

    def _construir_estado(self) -> None:
        barra = self.statusBar()
        self._total = QLabel("0 registros")
        self._total.setStyleSheet("color:#6B7684;padding-right:14px;")
        # Con el ingreso desactivado, el nombre de la barra no está respaldado por
        # una contraseña: tiene que verse distinto para que nadie lo confunda con
        # una sesión autenticada.
        if ingreso_obligatorio():
            self._usuario = QLabel(self._servicio.usuario)
            self._usuario.setStyleSheet("color:#6B7684;padding-right:14px;")
        else:
            self._usuario = QLabel(f"sin ingreso · {self._servicio.usuario}")
            self._usuario.setStyleSheet("color:#A50310;padding-right:14px;")
            self._usuario.setToolTip(
                "El ingreso con contraseña está desactivado en la configuración: "
                "los cambios se registran a nombre de esta cuenta sin verificarla."
            )
        barra.addPermanentWidget(self._total)
        barra.addPermanentWidget(self._usuario)
        self._actualizar_total()

    def _cablear(self) -> None:
        self.formulario.movimiento_creado.connect(self._al_registrar)
        self.formulario.error_validacion.connect(self._al_error)
        self.grid.mensaje.connect(self._avisar)
        self.grid.error_validacion.connect(self._al_error)
        # Un catálogo nuevo o renombrado tiene que aparecer en el formulario y en
        # el grid sin reiniciar la aplicación.
        self.configuracion.catalogo_cambiado.connect(self._al_cambiar_catalogo)
        self.configuracion.configuracion_cambiada.connect(self._al_cambiar_configuracion)
        for seccion, tecla in (
            (SECCION_REGISTRAR, "Ctrl+1"),
            (SECCION_MOVIMIENTOS, "Ctrl+2"),
            (SECCION_CONFIGURACION, "Ctrl+3"),
        ):
            QShortcut(QKeySequence(tecla), self).activated.connect(
                lambda destino=seccion: self.ir_a(destino)
            )

    # ---------------------------------------------------------------- navegación

    def ir_a(self, seccion: int) -> None:
        self._rail[seccion].setChecked(True)
        self._paginas.setCurrentIndex(seccion)
        if seccion == SECCION_MOVIMIENTOS:
            self.grid.mostrar_todos()
            self.grid.recargar()
        elif seccion == SECCION_CONFIGURACION:
            self.configuracion.recargar()
        elif seccion == SECCION_REGISTRAR:
            self.formulario.area.setFocus()

    @property
    def seccion_actual(self) -> int:
        return self._paginas.currentIndex()

    @property
    def pagina_actual(self) -> int:
        return self._paginas.currentIndex()

    # ------------------------------------------------------------------- eventos

    def _al_registrar(self, movimiento: MovimientoLeido) -> None:
        self.grid.agregar(movimiento)
        self._actualizar_total()
        referencia = movimiento.modelo or movimiento.codigo_inventario or "equipo"
        self._avisar(f"Entrada registrada · {referencia}")

    def _al_error(self, mensaje: str) -> None:
        self.statusBar().showMessage(mensaje, 6000)

    def _avisar(self, mensaje: str) -> None:
        self.statusBar().showMessage(mensaje, 4000)
        self._actualizar_total()

    def _al_cambiar_configuracion(self) -> None:
        """Reconnect with the URL just saved and refresh what depends on it."""
        reset_engine()
        self.formulario.refrescar_catalogos()
        self.grid.recargar()
        self._actualizar_total()
        self._avisar("Conexión actualizada")

    def _al_cambiar_catalogo(self) -> None:
        self.formulario.refrescar_catalogos()
        self.grid.recargar()
        self._avisar("Catálogo actualizado")

    def _actualizar_total(self) -> None:
        try:
            total = self._servicio.resumen().total
        except Exception:  # pragma: no cover - red caída a mitad de sesión
            total = 0
        self._total.setText(f"{total} registros")
