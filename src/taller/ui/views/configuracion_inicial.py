"""Asistente de primera ejecución.

Una aplicación empaquetada no puede pedirle al usuario que edite un archivo de
configuración. La primera vez que se abre, pregunta lo mínimo y lo deja andando:

1. **La marca**: nombre de la organización y el logo que va a mostrarse.
2. **La conexión**: servidor, puerto, usuario, contraseña y base.
3. **Las tablas**: se crean desde acá, sin abrir una terminal.

El botón de guardar no se habilita hasta que la conexión se probó de verdad: es la
diferencia entre un instalador que funciona y uno que guarda datos que después no
sirven.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from taller.arranque import (
    ConfiguracionArranque,
    aplicar_migraciones,
    campos_desde_url,
    copiar_logo,
    guardar_configuracion,
    url_desde_campos,
)
from taller.ui.iconos import icono
from taller.ui.tema import COLORES

Verificador = Callable[[str], tuple[bool, str]]
Migrador = Callable[[str], None]

ALTO_PREVIA = 96


def probar_conexion_real(url: str) -> tuple[bool, str]:
    """Try the URL with a real connection and return a message worth reading."""
    from sqlalchemy import create_engine, text

    try:
        motor = create_engine(url, connect_args={"connect_timeout": 5})
        with motor.connect() as conexion:
            conexion.execute(text("select 1"))
        motor.dispose()
    except Exception as exc:  # noqa: BLE001 - el mensaje se muestra tal cual
        return False, str(exc).splitlines()[0][:220]
    return True, "Conexión correcta."


def _etiqueta(texto: str) -> QLabel:
    etiqueta = QLabel(texto)
    etiqueta.setObjectName("EtiquetaCampo")
    return etiqueta


class ConfiguracionInicialDialog(QDialog):
    """Pedir marca y conexión, crear las tablas y dejar la aplicación lista."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        verificador: Verificador | None = None,
        migrador: Migrador | None = None,
        inicial: ConfiguracionArranque | None = None,
    ) -> None:
        super().__init__(parent)
        self._verificador = verificador or probar_conexion_real
        self._migrador = migrador or aplicar_migraciones
        self._logo_elegido: Path | None = None
        self._conexion_ok = False
        self._tablas_creadas = False

        self.setWindowTitle("Configuración inicial")
        self.setMinimumWidth(720)
        self._construir()
        if inicial is not None:
            self._prellenar(inicial)

    # ------------------------------------------------------------------ armado

    def _construir(self) -> None:
        titulo = QLabel("Puesta en marcha")
        titulo.setObjectName("TituloVista")
        subtitulo = QLabel(
            "Estos datos se guardan en tu carpeta de usuario. Solo se piden una vez."
        )
        subtitulo.setObjectName("SubtituloVista")

        self.nombre = QLineEdit("Taller de equipos")
        self.organizacion = QLineEdit()
        self.organizacion.setPlaceholderText("Nombre de la organización")
        self.descripcion = QLineEdit()
        self.descripcion.setPlaceholderText("Se muestra al lado del nombre")

        self.boton_logo = QPushButton("Elegir logo…")
        self.boton_logo.setIcon(icono("editar", COLORES["gris-700"]))
        self.previa = QLabel("Sin logo: se usa el símbolo genérico")
        self.previa.setObjectName("SubtituloVista")
        self.previa.setFixedHeight(ALTO_PREVIA)
        self.previa.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

        self.host = QLineEdit("localhost")
        self.puerto = QSpinBox()
        self.puerto.setRange(1, 65535)
        self.puerto.setValue(5432)
        self.usuario = QLineEdit("taller_app")
        self.contrasena = QLineEdit()
        self.contrasena.setEchoMode(QLineEdit.EchoMode.Password)
        self.base = QLineEdit("taller")

        self.error = QLabel()
        self.error.setObjectName("ErrorValidacion")
        self.error.setWordWrap(True)
        self.error.hide()
        self.exito = QLabel()
        self.exito.setObjectName("AvisoRevision")
        self.exito.setWordWrap(True)
        self.exito.hide()

        self.boton_probar = QPushButton("Probar conexión")
        self.boton_probar.clicked.connect(self.probar)
        self.boton_tablas = QPushButton("Crear tablas")
        self.boton_tablas.setEnabled(False)
        self.boton_tablas.clicked.connect(self.crear_tablas)
        self.boton_guardar = QPushButton("Guardar y continuar")
        self.boton_guardar.setObjectName("BotonPrimario")
        self.boton_guardar.setIcon(icono("guardar", COLORES["blanco"]))
        self.boton_guardar.setEnabled(False)
        self.boton_guardar.clicked.connect(self.guardar)
        cancelar = QPushButton("Cancelar")
        cancelar.clicked.connect(self.reject)

        marca = QGridLayout()
        marca.setHorizontalSpacing(16)
        marca.setVerticalSpacing(10)
        marca.addWidget(_etiqueta("Nombre visible"), 0, 0)
        marca.addWidget(_etiqueta("Organización"), 0, 1)
        marca.addWidget(self.nombre, 1, 0)
        marca.addWidget(self.organizacion, 1, 1)
        marca.addWidget(_etiqueta("Descripción"), 2, 0)
        marca.addWidget(_etiqueta("Logo"), 2, 1)
        marca.addWidget(self.descripcion, 3, 0)
        fila_logo = QHBoxLayout()
        fila_logo.setSpacing(10)
        fila_logo.addWidget(self.boton_logo)
        fila_logo.addWidget(self.previa, 1)
        contenedor_logo = QWidget()
        contenedor_logo.setObjectName("Contenedor")
        contenedor_logo.setLayout(fila_logo)
        marca.addWidget(contenedor_logo, 3, 1)
        marca.setColumnStretch(0, 1)
        marca.setColumnStretch(1, 1)

        base_datos = QGridLayout()
        base_datos.setHorizontalSpacing(16)
        base_datos.setVerticalSpacing(10)
        base_datos.addWidget(_etiqueta("Servidor"), 0, 0)
        base_datos.addWidget(_etiqueta("Puerto"), 0, 1)
        base_datos.addWidget(_etiqueta("Usuario"), 0, 2)
        base_datos.addWidget(self.host, 1, 0)
        base_datos.addWidget(self.puerto, 1, 1)
        base_datos.addWidget(self.usuario, 1, 2)
        base_datos.addWidget(_etiqueta("Contraseña"), 2, 0)
        base_datos.addWidget(_etiqueta("Base de datos"), 2, 1)
        base_datos.addWidget(self.contrasena, 3, 0)
        base_datos.addWidget(self.base, 3, 1)
        base_datos.setColumnStretch(0, 2)
        base_datos.setColumnStretch(1, 1)
        base_datos.setColumnStretch(2, 1)

        acciones = QHBoxLayout()
        acciones.setSpacing(8)
        acciones.addWidget(self.boton_probar)
        acciones.addWidget(self.boton_tablas)
        acciones.addStretch(1)
        acciones.addWidget(cancelar)
        acciones.addWidget(self.boton_guardar)

        contenido = QWidget()
        contenido.setObjectName("Contenedor")
        columna = QVBoxLayout(contenido)
        columna.setContentsMargins(24, 20, 24, 18)
        columna.setSpacing(10)
        columna.addWidget(titulo)
        columna.addWidget(subtitulo)
        columna.addWidget(self._divisor())
        columna.addWidget(_etiqueta("1 · Identidad"))
        columna.addLayout(marca)
        columna.addWidget(self._divisor())
        columna.addWidget(_etiqueta("2 · Conexión a la base de datos"))
        columna.addLayout(base_datos)
        aviso_rol = QLabel(
            "Usá un rol de aplicación con permiso solo sobre esta base, "
            "nunca el superusuario «postgres»."
        )
        aviso_rol.setObjectName("AyudaCampo")
        aviso_rol.setWordWrap(True)
        columna.addWidget(aviso_rol)
        columna.addWidget(self.error)
        columna.addWidget(self.exito)
        columna.addStretch(1)
        columna.addLayout(acciones)

        caja = QVBoxLayout(self)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.addWidget(contenido)

        self.boton_logo.clicked.connect(self.elegir_logo)

    def _prellenar(self, inicial: ConfiguracionArranque) -> None:
        """Reabrir la configuración con lo que ya está guardado."""
        if inicial.nombre:
            self.nombre.setText(inicial.nombre)
        self.organizacion.setText(inicial.organizacion)
        self.descripcion.setText(inicial.descripcion)
        if inicial.logo is not None and inicial.logo.is_file():
            self._logo_elegido = inicial.logo
            previa = QPixmap(str(inicial.logo))
            if not previa.isNull():
                self.previa.setPixmap(previa.scaledToHeight(ALTO_PREVIA))

        campos = campos_desde_url(inicial.database_url) if inicial.database_url else {}
        if campos:
            self.host.setText(str(campos.get("host", "")))
            self.puerto.setValue(int(campos.get("puerto", 5432)))  # type: ignore[arg-type]
            self.usuario.setText(str(campos.get("usuario", "")))
            self.contrasena.setText(str(campos.get("contrasena", "")))
            self.base.setText(str(campos.get("base", "")))

    @staticmethod
    def _divisor() -> QFrame:
        linea = QFrame()
        linea.setObjectName("Divisor")
        linea.setFixedHeight(1)
        return linea

    # ------------------------------------------------------------------ marca

    def elegir_logo(self) -> None:
        elegido, _filtro = QFileDialog.getOpenFileName(
            self, "Elegir el logo", "", "Imágenes (*.png *.jpg *.jpeg *.svg)"
        )
        if not elegido:
            return
        self._logo_elegido = Path(elegido)
        pixmap = QPixmap(elegido)
        if pixmap.isNull():
            self.previa.setText(f"Logo elegido: {Path(elegido).name}")
        else:
            self.previa.setPixmap(pixmap.scaledToHeight(ALTO_PREVIA))

    # ------------------------------------------------------------------ base

    def url(self) -> str:
        return url_desde_campos(
            self.host.text(),
            self.puerto.value(),
            self.usuario.text(),
            self.contrasena.text(),
            self.base.text(),
        )

    def probar(self) -> bool:
        self._conexion_ok = False
        self.boton_guardar.setEnabled(False)
        self.boton_tablas.setEnabled(False)
        ok, mensaje = self._verificador(self.url())
        if not ok:
            self._avisar(mensaje)
            return False
        self._conexion_ok = True
        self.error.hide()
        self.boton_tablas.setEnabled(True)
        self.boton_guardar.setEnabled(True)
        self._celebrar("Conexión correcta. El siguiente paso es crear las tablas.")
        return True

    def crear_tablas(self) -> bool:
        if not self._conexion_ok:
            self._avisar("Probá la conexión antes de crear las tablas.")
            return False
        try:
            self._migrador(self.url())
        except Exception as exc:  # noqa: BLE001 - el motivo se muestra tal cual
            self._avisar(f"No se pudieron crear las tablas: {exc}")
            return False
        self._tablas_creadas = True
        self._celebrar("Tablas creadas. Ya podés guardar y continuar.")
        return True

    def guardar(self) -> bool:
        if not self._conexion_ok:
            self._avisar("Probá la conexión antes de guardar.")
            return False
        if not self.nombre.text().strip():
            self._avisar("El nombre visible no puede quedar vacío.")
            return False
        try:
            logo = copiar_logo(self._logo_elegido) if self._logo_elegido else None
            guardar_configuracion(
                ConfiguracionArranque(
                    database_url=self.url(),
                    nombre=self.nombre.text().strip(),
                    organizacion=self.organizacion.text().strip(),
                    descripcion=self.descripcion.text().strip(),
                    logo=logo,
                )
            )
        except OSError as exc:
            self._avisar(f"No se pudo guardar la configuración: {exc}")
            return False
        self.accept()
        return True

    # ------------------------------------------------------------------ avisos

    def _avisar(self, mensaje: str) -> None:
        self.exito.hide()
        self.error.setText(mensaje)
        self.error.show()

    def _celebrar(self, mensaje: str) -> None:
        self.error.hide()
        self.exito.setText(mensaje)
        self.exito.show()
