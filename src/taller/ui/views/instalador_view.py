"""Wizard gráfico de instalación y desinstalación.

Dos botones grandes y una lista de lo que hay en la máquina. Sin rutas que recordar,
sin comandos que copiar y sin permisos de administrador: si algo necesita más
privilegios, lo dice acá mismo.

Se abre con ``--instalar`` o ``--desinstalar``, o desde el menú del programa.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from taller import instalador
from taller.ui import tema
from taller.ui.iconos import icono
from taller.ui.marca import cargar_marca

COLORES = tema.COLORES


class DialogoInstalador(QDialog):
    """Instalar el programa en esta máquina, o quitarlo."""

    def __init__(self, parent: QWidget | None = None, *, modo: str = "instalar") -> None:
        super().__init__(parent)
        self._modo = modo
        self.setWindowTitle("Instalar" if modo == "instalar" else "Desinstalar")
        self.setMinimumWidth(640)
        self._construir()

    # ------------------------------------------------------------------ armado

    def _construir(self) -> None:
        marca = cargar_marca()

        encabezado = QHBoxLayout()
        encabezado.setSpacing(12)
        logo = QLabel()
        pixmap = QPixmap(str(marca.logo))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaledToHeight(48))
        encabezado.addWidget(logo)
        titulos = QVBoxLayout()
        titulos.setSpacing(2)
        titulo = (
            "Instalar en esta computadora"
            if self._modo == "instalar"
            else "Quitar de esta computadora"
        )
        nombre = QLabel(titulo)
        nombre.setObjectName("TituloVista")
        detalle = QLabel(
            "Elegí dónde. No hace falta contraseña de administrador y no se toca la base de datos."
            if self._modo == "instalar"
            else "Se quita el programa. Tus datos y la base quedan donde están."
        )
        detalle.setObjectName("SubtituloVista")
        detalle.setWordWrap(True)
        titulos.addWidget(nombre)
        titulos.addWidget(detalle)
        encabezado.addLayout(titulos, 1)

        tarjeta = QFrame()
        tarjeta.setObjectName("Tarjeta")
        cuerpo = QVBoxLayout(tarjeta)
        cuerpo.setContentsMargins(18, 16, 18, 18)
        cuerpo.setSpacing(10)

        if self._modo == "instalar":
            self._armar_instalacion(cuerpo)
        else:
            self._armar_desinstalacion(cuerpo)

        self.resultado = QLabel()
        self.resultado.setObjectName("AvisoRevision")
        self.resultado.setWordWrap(True)
        self.resultado.hide()

        caja = QVBoxLayout(self)
        caja.setContentsMargins(20, 18, 20, 18)
        caja.setSpacing(12)
        caja.addLayout(encabezado)
        caja.addWidget(tarjeta)
        caja.addWidget(self.resultado)

    def _armar_instalacion(self, cuerpo: QVBoxLayout) -> None:
        ya = instalador.detectar()
        actual = instalador.raiz_del_programa()

        self.para_usuario = QRadioButton("Solo para mí")
        self.para_usuario.setChecked(True)
        self.destino_usuario = QLineEdit(str(instalador.destino_usuario()))
        self.destino_usuario.setReadOnly(True)

        self.para_todos = QRadioButton("Para todos los usuarios de esta computadora")
        self.destino_sistema = QLineEdit(str(instalador.destino_sistema()))
        self.destino_sistema.setReadOnly(True)
        if instalador.es_windows():
            self.destino_sistema.setToolTip(
                "En Windows puede pedir permisos de administrador."
            )

        grupo = QButtonGroup(self)
        grupo.addButton(self.para_usuario)
        grupo.addButton(self.para_todos)
        self.para_usuario.toggled.connect(self._actualizar_destino)

        cuerpo.addWidget(self.para_usuario)
        cuerpo.addWidget(self.destino_usuario)
        cuerpo.addSpacing(6)
        cuerpo.addWidget(self.para_todos)
        cuerpo.addWidget(self.destino_sistema)
        cuerpo.addSpacing(8)

        self.aviso_existente = QLabel()
        self.aviso_existente.setObjectName("AyudaCampo")
        self.aviso_existente.setWordWrap(True)

        from taller import __version__
        from taller import instalador as modulo_instalador

        destino = instalador.destino_usuario()
        es_actualizacion = modulo_instalador.es_actualizacion(destino)
        if es_actualizacion:
            instalada = ya[0].version if ya else "?"
            self.aviso_existente.setText(
                f"Actualización: la copia instalada es la {instalada} y este programa "
                f"es la {__version__}. La nueva reemplaza a la vieja y TU "
                "configuración (nombre, logo, conexión, usuarios) no se toca."
            )
        elif ya:
            rutas = ", ".join(str(i.ruta) for i in ya)
            self.aviso_existente.setText(
                f"Ya hay una instalación en {rutas}; se reemplaza por la nueva, y la configuración queda."
            )
        else:
            self.aviso_existente.setText(
                f"Se van a copiar ≈ 250 MB de {actual} a {instalador.destino_usuario()}. "
                "Quedan el lanzador en el menú de aplicaciones y la configuración de la app."
            )
        cuerpo.addWidget(self.aviso_existente)

        self.boton = QPushButton("Actualizar" if es_actualizacion else "Instalar")
        self.boton.setObjectName("BotonPrimario")
        self.boton.setIcon(icono("guardar", COLORES["blanco"]))
        self.boton.clicked.connect(self.instalar)
        self.boton.setDefault(True)

        acciones = QHBoxLayout()
        acciones.addWidget(self.boton)
        acciones.addWidget(QPushButton("Cancelar", clicked=self.reject))
        acciones.addStretch(1)
        cuerpo.addLayout(acciones)
        self._actualizar_destino()

    def _armar_desinstalacion(self, cuerpo: QVBoxLayout) -> None:
        encontradas = instalador.detectar()
        if encontradas:
            for hallada in encontradas:
                fila = QHBoxLayout()
                etiqueta = QLabel(str(hallada.ruta))
                etiqueta.setObjectName("ValorDetalle")
                etiqueta.setWordWrap(True)
                fila.addWidget(etiqueta, 1)
                version = hallada.version or "versión sin dato"
                tamano = QLabel(f"{version} · {hallada.tamano_mb} MB")
                tamano.setObjectName("ClaveDetalle")
                fila.addWidget(tamano)
                cuerpo.addLayout(fila)
        else:
            vacio = QLabel(
                "No encontré ninguna instalación del programa en esta computadora."
            )
            vacio.setWordWrap(True)
            cuerpo.addWidget(vacio)

        self.con_configuracion = QCheckBox("Borrar también la configuración guardada")
        self.con_configuracion.setToolTip(
            "Nombre, logo, conexión y el ajuste del ingreso. La base de datos no se toca."
        )
        cuerpo.addSpacing(6)
        cuerpo.addWidget(self.con_configuracion)
        aviso = QLabel(f"Queda en {instalador.carpeta_configuracion()}")
        aviso.setObjectName("AyudaCampo")
        aviso.setWordWrap(True)
        cuerpo.addWidget(aviso)

        self.boton = QPushButton("Desinstalar")
        self.boton.setObjectName("BotonPeligro")
        self.boton.setIcon(icono("eliminar", COLORES["blanco"]))
        self.boton.clicked.connect(self.desinstalar)
        self.boton.setEnabled(bool(encontradas))

        acciones = QHBoxLayout()
        acciones.addWidget(self.boton)
        acciones.addWidget(QPushButton("Cancelar", clicked=self.reject))
        acciones.addStretch(1)
        cuerpo.addSpacing(8)
        cuerpo.addLayout(acciones)

    # ------------------------------------------------------------------ lógica

    def _destino_elegido(self) -> Path:
        return (
            instalador.destino_usuario()
            if self.para_usuario.isChecked()
            else instalador.destino_sistema()
        )

    def _actualizar_destino(self) -> None:
        propio = self.para_usuario.isChecked()
        self.destino_usuario.setEnabled(propio)
        self.destino_sistema.setEnabled(not propio)

    def instalar(self) -> bool:
        self.boton.setEnabled(False)
        self.boton.setText("Instalando…")
        resultado = instalador.instalar(self._destino_elegido())
        self.boton.setEnabled(True)
        self.boton.setText("Instalar")
        self._mostrar(resultado)
        if resultado.ok:
            self.boton.setText("Listo")
            self.boton.setEnabled(False)
        return resultado.ok

    def desinstalar(self) -> bool:
        self.boton.setEnabled(False)
        self.boton.setText("Quitando…")
        resultado = instalador.desinstalar(self.con_configuracion.isChecked())
        self.boton.setEnabled(True)
        self.boton.setText("Desinstalar")
        self._mostrar(resultado)
        if resultado.ok:
            self.boton.setText("Listo")
            self.boton.setEnabled(False)
        return resultado.ok

    def _mostrar(self, resultado: instalador.Resultado) -> None:
        lineas = [resultado.mensaje, *resultado.detalles]
        self.resultado.setText("\n".join(f"· {linea}" for linea in lineas if linea))
        self.resultado.setObjectName(
            "AvisoRevision" if resultado.ok else "ErrorValidacion"
        )
        # Cambiar el nombre de objeto no vuelve a aplicar el estilo por sí solo.
        self.resultado.setStyleSheet(
            f"color: {COLORES['verde-700'] if resultado.ok else COLORES['rojo-700']};"
        )
        self.resultado.show()
