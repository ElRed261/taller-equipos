"""Pantalla de ingreso y creación del primer administrador.

La auditoría dice quién hizo cada cambio, y eso solo vale si para entrar hace
falta una contraseña. Por eso el nombre no se escribe libremente en el formulario
de movimientos: se elige acá, una vez, contra la base.

Dos mensajes y nada más: uno para el fallo de credenciales (sin decir si el
usuario existe, para no regalar la lista de cuentas) y otro para cuando la clave
que se quiere fijar no sirve.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from taller.seguridad import LARGO_MINIMO, clave_aceptable
from taller.servicios import ServicioTaller
from taller.ui import tema
from taller.ui.iconos import icono
from taller.ui.marca import cargar_marca

COLORES = tema.COLORES
ALTO_LOGO = 56


def _campo(etiqueta: str, *, oculto: bool = False) -> tuple[QLabel, QLineEdit]:
    titulo = QLabel(etiqueta)
    titulo.setObjectName("EtiquetaCampo")
    entrada = QLineEdit()
    if oculto:
        entrada.setEchoMode(QLineEdit.EchoMode.Password)
    return titulo, entrada


class DialogoIngreso(QDialog):
    """Pedir usuario y contraseña. ``usuario`` queda con el nombre autenticado."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        autenticador=ServicioTaller.autenticar,  # noqa: ANN001 - inyectable en pruebas
    ) -> None:
        super().__init__(parent)
        self._autenticador = autenticador
        self.usuario: str | None = None
        self.es_admin = False

        self.setWindowTitle("Entrar")
        self.setMinimumWidth(420)
        self._construir()

    # ------------------------------------------------------------------ armado

    def _construir(self) -> None:
        marca = cargar_marca()

        encabezado = QHBoxLayout()
        encabezado.setSpacing(12)
        logo = QLabel()
        pixmap = QPixmap(str(marca.logo))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaledToHeight(ALTO_LOGO))
        encabezado.addWidget(logo)

        titulos = QVBoxLayout()
        titulos.setSpacing(2)
        nombre = QLabel(marca.nombre)
        nombre.setObjectName("TituloVista")
        detalle = QLabel(marca.descripcion or marca.organizacion)
        detalle.setObjectName("SubtituloVista")
        detalle.setWordWrap(True)
        titulos.addWidget(nombre)
        titulos.addWidget(detalle)
        encabezado.addLayout(titulos, 1)

        tarjeta = QFrame()
        tarjeta.setObjectName("Tarjeta")
        formulario = QVBoxLayout(tarjeta)
        formulario.setContentsMargins(18, 16, 18, 18)
        formulario.setSpacing(8)

        rotulo_usuario, self.usuario_entrada = _campo("Usuario")
        rotulo_clave, self.clave = _campo("Contraseña", oculto=True)
        formulario.addWidget(rotulo_usuario)
        formulario.addWidget(self.usuario_entrada)
        formulario.addWidget(rotulo_clave)
        formulario.addWidget(self.clave)

        self.error = QLabel()
        self.error.setObjectName("ErrorValidacion")
        self.error.setWordWrap(True)
        self.error.hide()
        formulario.addWidget(self.error)

        self.boton_entrar = QPushButton("Entrar")
        self.boton_entrar.setObjectName("BotonPrimario")
        self.boton_entrar.setIcon(icono("ingreso", COLORES["blanco"]))
        self.boton_entrar.setDefault(True)
        self.boton_entrar.clicked.connect(self.intentar)

        self.boton_salir = QPushButton("Salir")
        self.boton_salir.clicked.connect(self.reject)

        acciones = QHBoxLayout()
        acciones.addWidget(self.boton_entrar)
        acciones.addWidget(self.boton_salir)
        acciones.addStretch(1)
        formulario.addSpacing(4)
        formulario.addLayout(acciones)

        caja = QVBoxLayout(self)
        caja.setContentsMargins(20, 18, 20, 18)
        caja.setSpacing(14)
        caja.addLayout(encabezado)
        caja.addWidget(tarjeta)

        # Enter en cualquiera de los dos campos envía: es lo que hace todo el mundo.
        for entrada in (self.usuario_entrada, self.clave):
            entrada.returnPressed.connect(self.intentar)
        self.usuario_entrada.setFocus(Qt.FocusReason.OtherFocusReason)

    # ------------------------------------------------------------------ lógica

    def intentar(self) -> bool:
        nombre = self.usuario_entrada.text().strip()
        if not nombre or not self.clave.text():
            self._mostrar_error("Escribí el usuario y la contraseña.")
            return False

        cuenta = self._autenticador(nombre, self.clave.text())
        if cuenta is None:
            # Un solo mensaje: no se revela si el usuario existe o la clave falló.
            self._mostrar_error("Usuario o contraseña incorrectos.")
            self.clave.clear()
            self.clave.setFocus(Qt.FocusReason.OtherFocusReason)
            return False

        self.usuario = cuenta.nombre
        self.es_admin = cuenta.es_admin
        self.accept()
        return True

    def _mostrar_error(self, texto: str) -> None:
        self.error.setText(texto)
        self.error.show()


class DialogoPrimerAdministrador(QDialog):
    """Crear la cuenta que puede administrar el sistema.

    Si no hay ninguna, el sistema no tiene quién lo administre. Se pide antes que
    cualquier otra cosa, y esa cuenta puede dar de alta a las demás.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        existentes: list[str] | None = None,
        creador=ServicioTaller.crear_administrador,  # noqa: ANN001 - inyectable
    ) -> None:
        super().__init__(parent)
        self._creador = creador
        self._existentes = existentes or []
        self.usuario: str | None = None

        self.setWindowTitle("Primera cuenta")
        self.setMinimumWidth(460)
        self._construir()

    def _construir(self) -> None:
        titulo = QLabel("Creá la primera cuenta")
        titulo.setObjectName("TituloVista")
        detalle = QLabel(
            "No hay ninguna cuenta administradora. Esta cuenta va a poder dar de alta "
            "a las demás y es la que queda registrada cuando alguien administra."
        )
        detalle.setObjectName("SubtituloVista")
        detalle.setWordWrap(True)

        self.nombre = QLineEdit()
        self.nombre.setPlaceholderText("Tu nombre o el de quien administre")
        self.clave = QLineEdit()
        self.clave.setEchoMode(QLineEdit.EchoMode.Password)
        self.repetida = QLineEdit()
        self.repetida.setEchoMode(QLineEdit.EchoMode.Password)

        ayuda = QLabel(f"Al menos {LARGO_MINIMO} caracteres. Que no la sepas de memoria.")
        ayuda.setObjectName("AyudaCampo")
        ayuda.setWordWrap(True)

        self.error = QLabel()
        self.error.setObjectName("ErrorValidacion")
        self.error.setWordWrap(True)
        self.error.hide()

        self.boton_crear = QPushButton("Crear y entrar")
        self.boton_crear.setObjectName("BotonPrimario")
        self.boton_crear.setIcon(icono("ingreso", COLORES["blanco"]))
        self.boton_crear.setDefault(True)
        self.boton_crear.clicked.connect(self.crear)

        tarjeta = QFrame()
        tarjeta.setObjectName("Tarjeta")
        formulario = QVBoxLayout(tarjeta)
        formulario.setContentsMargins(18, 16, 18, 18)
        formulario.setSpacing(8)
        for rotulo, entrada in (
            ("Usuario", self.nombre),
            ("Contraseña", self.clave),
            ("Repetí la contraseña", self.repetida),
        ):
            etiqueta = QLabel(rotulo)
            etiqueta.setObjectName("EtiquetaCampo")
            formulario.addWidget(etiqueta)
            formulario.addWidget(entrada)
        formulario.addWidget(ayuda)
        formulario.addWidget(self.error)
        formulario.addSpacing(4)
        formulario.addWidget(self.boton_crear)

        caja = QVBoxLayout(self)
        caja.setContentsMargins(20, 18, 20, 18)
        caja.setSpacing(14)
        caja.addWidget(titulo)
        caja.addWidget(detalle)
        caja.addWidget(tarjeta)

        for entrada in (self.nombre, self.clave, self.repetida):
            entrada.returnPressed.connect(self.crear)
        self.nombre.setFocus(Qt.FocusReason.OtherFocusReason)

    def crear(self) -> bool:
        nombre = self.nombre.text().strip()
        if not nombre:
            self._error("Escribí un nombre de usuario.")
            return False
        if self.clave.text() != self.repetida.text():
            self._error("Las dos contraseñas no coinciden.")
            self.repetida.clear()
            self.repetida.setFocus(Qt.FocusReason.OtherFocusReason)
            return False
        motivo = clave_aceptable(self.clave.text())
        if motivo:
            self._error(motivo)
            return False

        try:
            cuenta = self._creador(nombre, self.clave.text())
        except ValueError as error:
            self._error(str(error))
            return False

        self.usuario = cuenta.nombre
        self.accept()
        return True

    def _error(self, texto: str) -> None:
        self.error.setText(texto)
        self.error.show()


class DialogoClave(QDialog):
    """Pedir una contraseña dos veces y entregarla ya validada.

    Se usa tanto para una cuenta nueva como para cambiar la de alguien. La regla
    de aceptación es una sola en todo el programa: la de ``clave_aceptable``.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        titulo: str = "Contraseña",
        detalle: str = "",
        nombre: str = "",
    ) -> None:
        super().__init__(parent)
        self.clave: str | None = None

        self.setWindowTitle(titulo)
        self.setMinimumWidth(420)

        self.nombre = QLineEdit(nombre)
        self.entrada = QLineEdit()
        self.entrada.setEchoMode(QLineEdit.EchoMode.Password)
        self.repetida = QLineEdit()
        self.repetida.setEchoMode(QLineEdit.EchoMode.Password)

        self.error = QLabel()
        self.error.setObjectName("ErrorValidacion")
        self.error.setWordWrap(True)
        self.error.hide()

        ayuda = QLabel(f"Al menos {LARGO_MINIMO} caracteres.")
        ayuda.setObjectName("AyudaCampo")

        tarjeta = QFrame()
        tarjeta.setObjectName("Tarjeta")
        formulario = QVBoxLayout(tarjeta)
        formulario.setContentsMargins(18, 16, 18, 18)
        formulario.setSpacing(8)

        if not nombre:
            etiqueta_nombre = QLabel("Usuario")
            etiqueta_nombre.setObjectName("EtiquetaCampo")
            formulario.addWidget(etiqueta_nombre)
            formulario.addWidget(self.nombre)
        for rotulo, campo in (
            ("Contraseña", self.entrada),
            ("Repetí la contraseña", self.repetida),
        ):
            etiqueta = QLabel(rotulo)
            etiqueta.setObjectName("EtiquetaCampo")
            formulario.addWidget(etiqueta)
            formulario.addWidget(campo)
        formulario.addWidget(ayuda)
        formulario.addWidget(self.error)

        self.boton = QPushButton("Guardar")
        self.boton.setObjectName("BotonPrimario")
        self.boton.setDefault(True)
        self.boton.clicked.connect(self.aceptar)

        acciones = QHBoxLayout()
        acciones.addWidget(self.boton)
        acciones.addWidget(QPushButton("Cancelar", clicked=self.reject))
        acciones.addStretch(1)
        formulario.addSpacing(4)
        formulario.addLayout(acciones)

        caja = QVBoxLayout(self)
        caja.setContentsMargins(20, 18, 20, 18)
        caja.setSpacing(10)
        cabecera = QLabel(titulo)
        cabecera.setObjectName("TituloVista")
        caja.addWidget(cabecera)
        if detalle:
            texto = QLabel(detalle)
            texto.setObjectName("SubtituloVista")
            texto.setWordWrap(True)
            caja.addWidget(texto)
        caja.addWidget(tarjeta)

        for campo in (self.nombre, self.entrada, self.repetida):
            campo.returnPressed.connect(self.aceptar)
        self.entrada.setFocus(Qt.FocusReason.OtherFocusReason)

    def aceptar(self) -> bool:
        if not self.nombre.text().strip():
            self._error("Escribí un nombre de usuario.")
            return False
        if self.entrada.text() != self.repetida.text():
            self._error("Las dos contraseñas no coinciden.")
            self.repetida.clear()
            self.repetida.setFocus(Qt.FocusReason.OtherFocusReason)
            return False
        motivo = clave_aceptable(self.entrada.text())
        if motivo:
            self._error(motivo)
            return False
        self.clave = self.entrada.text()
        self.accept()
        return True

    def _error(self, texto: str) -> None:
        self.error.setText(texto)
        self.error.show()
