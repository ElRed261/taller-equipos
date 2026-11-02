"""Configuración del sistema: los tres catálogos maestros.

Reemplaza a la sección «Revisión» del rail. La revisión no se pierde: sigue
disponible como chip dentro de Movimientos, que es donde se trabaja con esas
filas.

Cada pestaña ofrece lo mismo —crear, renombrar, desactivar y fusionar— porque el
problema es el mismo en las tres: el archivo legado dejó 190 áreas y 38 soportes
escritos de mil maneras. Fusionar es la herramienta que deshace eso sin perder
historial, y por eso muestra cuántos movimientos se van a mover antes de tocarlos.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from taller.arranque import campos_desde_url, cargar_configuracion
from taller.schemas.movimiento import CatalogoConUso, MovimientoLeido
from taller.servicios import ServicioTaller
from taller.ui.iconos import icono
from taller.ui.models.catalogo_table_model import CatalogoTableModel, ColumnaCatalogo
from taller.ui.models.filtro_movimientos import FiltroMovimientos
from taller.ui.models.historial_table_model import HistorialTableModel
from taller.ui.models.movimientos_table_model import Columna, MovimientosTableModel
from taller.ui.models.usuarios_table_model import UsuariosTableModel
from taller.ui.tema import COLORES

ETIQUETAS = {
    "tipo_equipo": ("Tipos de equipo", "CPU, impresora, monitor, laptop, UPS…"),
    "area": ("Áreas", "Los departamentos que entregan y reciben equipos."),
    "tecnico": ("Soportes técnicos", "Quiénes intervienen en cada reparación."),
}


class PanelCatalogo(QWidget):
    """One catalog: a table plus the four actions that keep it clean."""

    cambio = Signal()

    def __init__(
        self,
        servicio: ServicioTaller,
        dimension: str,
        titulo: str,
        descripcion: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._servicio = servicio
        self._dimension = dimension
        self._modelo = CatalogoTableModel()

        encabezado = QLabel(titulo)
        encabezado.setObjectName("TituloVista")
        detalle = QLabel(descripcion)
        detalle.setObjectName("SubtituloVista")

        self.tabla = QTableView()
        self.tabla.setModel(self._modelo)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(28)
        cabecera = self.tabla.horizontalHeader()
        cabecera.setSectionResizeMode(int(ColumnaCatalogo.NOMBRE), QHeaderView.ResizeMode.Stretch)
        cabecera.setSectionResizeMode(
            int(ColumnaCatalogo.ESTADO), QHeaderView.ResizeMode.Fixed
        )
        cabecera.setSectionResizeMode(
            int(ColumnaCatalogo.MOVIMIENTOS), QHeaderView.ResizeMode.Fixed
        )
        cabecera.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.tabla.setColumnWidth(int(ColumnaCatalogo.ESTADO), 90)
        self.tabla.setColumnWidth(int(ColumnaCatalogo.MOVIMIENTOS), 110)
        self.tabla.doubleClicked.connect(lambda _indice: self.renombrar())

        self.boton_nuevo = QPushButton("Nuevo")
        self.boton_nuevo.setObjectName("BotonPrimario")
        self.boton_nuevo.setIcon(icono("nuevo", COLORES["blanco"]))
        self.boton_renombrar = QPushButton("Renombrar")
        self.boton_desactivar = QPushButton("Desactivar")
        self.boton_fusionar = QPushButton("Fusionar dos…")
        self.boton_fusionar.setToolTip(
            "Elegí dos filas: los movimientos pasan a la que más historial tiene"
        )

        acciones = QHBoxLayout()
        acciones.setSpacing(8)
        acciones.addWidget(self.boton_nuevo)
        acciones.addWidget(self.boton_renombrar)
        acciones.addWidget(self.boton_desactivar)
        acciones.addWidget(self.boton_fusionar)
        acciones.addStretch(1)

        self.aviso = QLabel()
        self.aviso.setObjectName("ErrorValidacion")
        self.aviso.setWordWrap(True)
        self.aviso.hide()

        caja = QVBoxLayout(self)
        caja.setContentsMargins(18, 16, 18, 16)
        caja.setSpacing(8)
        caja.addWidget(encabezado)
        caja.addWidget(detalle)
        caja.addSpacing(6)
        caja.addWidget(self.tabla, 1)
        caja.addWidget(self.aviso)
        caja.addLayout(acciones)

        self.boton_nuevo.clicked.connect(self.nuevo)
        self.boton_renombrar.clicked.connect(self.renombrar)
        self.boton_desactivar.clicked.connect(self.alternar_activo)
        self.boton_fusionar.clicked.connect(self.fusionar)
        self.tabla.selectionModel().selectionChanged.connect(self._actualizar_botones)

        self.recargar()

    # ------------------------------------------------------------------ lectura

    def recargar(self) -> None:
        """Lista completa, siempre.

        Un registro desactivado no puede desaparecer: si no se ve, no hay forma
        de volver a activarlo, y la única salida sería editarlo por SQL.
        """
        try:
            filas = self._servicio.catalogo_con_uso(self._dimension, solo_activos=False)
        except Exception as exc:  # pragma: no cover - red caída
            self._avisar(str(exc))
            return
        self._modelo.reemplazar(filas)
        self._actualizar_botones()

    def seleccion(self) -> list[CatalogoConUso]:
        posiciones = sorted(
            {indice.row() for indice in self.tabla.selectionModel().selectedRows()}
        )
        return [self._modelo.fila(posicion) for posicion in posiciones]

    def _actualizar_botones(self, *_args: object) -> None:
        cantidad = len(self.seleccion())
        self.boton_renombrar.setEnabled(cantidad == 1)
        self.boton_desactivar.setEnabled(cantidad == 1)
        self.boton_fusionar.setEnabled(cantidad == 2)
        elegidos = self.seleccion()
        if len(elegidos) == 1:
            self.boton_desactivar.setText(
                "Reactivar" if not elegidos[0].activo else "Desactivar"
            )
        else:
            self.boton_desactivar.setText("Desactivar")

    # ----------------------------------------------------------------- acciones

    def nuevo(self) -> None:
        nombre, aceptado = QInputDialog.getText(self, "Nuevo registro", "Nombre:")
        if not (aceptado and nombre.strip()):
            return
        try:
            self._servicio.crear_catalogo(self._dimension, nombre)
        except (ValueError, LookupError) as exc:
            self._avisar(str(exc))
            return
        self.recargar()
        self.cambio.emit()

    def renombrar(self) -> None:
        elegidos = self.seleccion()
        if len(elegidos) != 1:
            return
        actual = elegidos[0]
        nombre, aceptado = QInputDialog.getText(
            self, "Renombrar", "Nombre nuevo:", text=actual.nombre
        )
        if not (aceptado and nombre.strip()) or nombre.strip() == actual.nombre:
            return
        try:
            self._servicio.renombrar_catalogo(self._dimension, actual.id, nombre)
        except (ValueError, LookupError) as exc:
            self._avisar(str(exc))
            return
        self.recargar()
        self.cambio.emit()

    def alternar_activo(self) -> None:
        """Desactivar o reactivar, según el estado de la fila elegida."""
        elegidos = self.seleccion()
        if len(elegidos) != 1:
            return
        fila = elegidos[0]
        if not fila.activo:
            try:
                self._servicio.activar_catalogo(self._dimension, fila.id)
            except (ValueError, LookupError) as exc:
                self._avisar(str(exc))
                return
            self.recargar()
            self.cambio.emit()
            self._avisar(f"«{fila.nombre}» quedó activo otra vez.", error=False)
            return
        self.desactivar()

    def desactivar(self) -> None:
        elegidos = self.seleccion()
        if len(elegidos) != 1:
            return
        fila = elegidos[0]
        detalle = (
            f"«{fila.nombre}» tiene {fila.movimientos} movimientos que conservan su historia.\n"
            "Dejará de aparecer al cargar datos nuevos."
            if fila.movimientos
            else f"«{fila.nombre}» no tiene movimientos asociados."
        )
        if not self._confirmar("Desactivar registro", f"{detalle}\n\n¿Continuar?"):
            return
        try:
            self._servicio.desactivar_catalogo(self._dimension, fila.id)
        except (ValueError, LookupError) as exc:
            self._avisar(str(exc))
            return
        self.recargar()
        self.cambio.emit()

    def fusionar(self) -> None:
        """Merge two rows: the one with more history survives.

        Deciding by history instead of asking "which one do you want to keep"
        avoids the classic mistake of absorbing the canonical name into a typo.
        """
        elegidos = self.seleccion()
        if len(elegidos) != 2:
            return
        destino, origen = sorted(elegidos, key=lambda fila: fila.movimientos, reverse=True)
        if origen.movimientos > destino.movimientos:  # pragma: no cover - defensivo
            destino, origen = origen, destino

        mensaje = (
            f"Se van a mover {origen.movimientos} movimientos de «{origen.nombre}» "
            f"a «{destino.nombre}».\n\n"
            f"«{origen.nombre}» quedará inactivo y su historial pasará a «{destino.nombre}»."
        )
        if not self._confirmar("Fusionar registros", mensaje):
            return
        try:
            movidos = self._servicio.fusionar_catalogo(self._dimension, origen.id, destino.id)
        except (ValueError, LookupError) as exc:
            self._avisar(str(exc))
            return
        self.recargar()
        self.cambio.emit()
        self._avisar(f"{movidos} movimientos pasaron a «{destino.nombre}».", error=False)

    # ------------------------------------------------------------------ apoyo

    def _confirmar(self, titulo: str, mensaje: str) -> bool:
        respuesta = QMessageBox.question(
            self,
            titulo,
            mensaje,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return respuesta == QMessageBox.StandardButton.Yes

    def _avisar(self, mensaje: str, *, error: bool = True) -> None:
        self.aviso.setText(mensaje)
        self.aviso.setObjectName("ErrorValidacion" if error else "AvisoRevision")
        self.aviso.setStyleSheet("")
        self.aviso.show()


class PanelAdministracion(QWidget):
    """Borrado definitivo de un registro, detrás de un interruptor.

    Eliminar un movimiento no es «desactivar»: se va, junto con sus vínculos y su
    auditoría de campos. Antes de eso el repositorio guarda un snapshot en
    ``movimiento_eliminado``, que es la única constancia que queda.

    El interruptor está apagado por defecto y el borrado pide escribir el código
    del equipo: son dos barreras para una acción que no se deshace.
    """

    cambio = Signal()
    mensaje = Signal(str)

    def __init__(self, servicio: ServicioTaller, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._servicio = servicio
        self._modelo = MovimientosTableModel(servicio, usuario=servicio.usuario)
        self._proxy = FiltroMovimientos()
        self._proxy.setSourceModel(self._modelo)

        titulo = QLabel("Administración")
        titulo.setObjectName("TituloVista")
        detalle = QLabel(
            "Eliminar un registro lo saca del sistema junto con su historial de cambios. "
            "Queda una copia en la tabla de eliminados."
        )
        detalle.setObjectName("SubtituloVista")
        detalle.setWordWrap(True)

        self.modo_admin = QCheckBox("Modo administrador")
        self.modo_admin.setToolTip("Habilita el borrado definitivo de registros")

        self.busqueda = QLineEdit()
        self.busqueda.setPlaceholderText("Buscar el registro a eliminar…")
        self.busqueda.setClearButtonEnabled(True)
        self.busqueda.addAction(
            icono("buscar", COLORES["gris-500"]),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self._temporizador = QTimer(self)
        self._temporizador.setSingleShot(True)
        self._temporizador.setInterval(250)
        self._temporizador.timeout.connect(
            lambda: self._proxy.set_texto(self.busqueda.text())
        )
        self.busqueda.textChanged.connect(lambda _texto: self._temporizador.start())

        self.tabla = QTableView()
        self.tabla.setModel(self._proxy)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(26)
        cabecera = self.tabla.horizontalHeader()
        cabecera.setStretchLastSection(True)
        for oculta in (
            Columna.DIAGNOSTICO,
            Columna.SERVICE_TAG,
            Columna.SOPORTE,
            Columna.TIPO,
            Columna.REVISION,
            Columna.NOTA,
        ):
            self.tabla.setColumnHidden(int(oculta), True)

        self.boton_eliminar = QPushButton("Eliminar registro…")
        self.boton_eliminar.setObjectName("BotonPeligro")
        self.boton_eliminar.setIcon(icono("eliminar", COLORES["blanco"]))
        self.boton_eliminar.setEnabled(False)

        acciones = QHBoxLayout()
        acciones.setSpacing(8)
        acciones.addWidget(self.modo_admin)
        acciones.addStretch(1)
        acciones.addWidget(self.boton_eliminar)

        caja = QVBoxLayout(self)
        caja.setContentsMargins(18, 16, 18, 16)
        caja.setSpacing(8)
        caja.addWidget(titulo)
        caja.addWidget(detalle)
        caja.addSpacing(6)
        caja.addWidget(self.busqueda)
        caja.addWidget(self.tabla, 1)
        caja.addLayout(acciones)

        self.modo_admin.toggled.connect(lambda _activo: self._actualizar_boton())
        self.tabla.selectionModel().selectionChanged.connect(self._actualizar_boton)
        self.boton_eliminar.clicked.connect(self.eliminar)

        self.recargar()

    # ------------------------------------------------------------------ estado

    def recargar(self) -> None:
        try:
            self._modelo.reemplazar(self._servicio.listar_movimientos())
        except Exception as exc:  # pragma: no cover - red caída
            self.mensaje.emit(str(exc))
        self._actualizar_boton()

    def seleccionado(self) -> MovimientoLeido | None:
        indices = self.tabla.selectionModel().selectedRows()
        if not indices:
            return None
        origen = self._proxy.mapToSource(indices[0])
        return self._modelo.fila(origen.row())

    def _actualizar_boton(self, *_args: object) -> None:
        self.boton_eliminar.setEnabled(
            self.modo_admin.isChecked() and self.seleccionado() is not None
        )

    # ---------------------------------------------------------------- borrado

    def eliminar(self) -> bool:
        fila = self.seleccionado()
        if fila is None or not self.modo_admin.isChecked():
            return False

        referencia = fila.codigo_inventario or fila.modelo or str(fila.id)
        confirmacion, aceptado = QInputDialog.getText(
            self,
            "Eliminar registro",
            f"Esto no se puede deshacer.\n\n"
            f"Escribí «{referencia}» para confirmar la eliminación de "
            f"«{fila.modelo or 'el equipo'}» del área {fila.area or '—'}:",
        )
        if not aceptado:
            return False
        if confirmacion.strip() != referencia:
            self.mensaje.emit("La confirmación no coincide: no se eliminó nada.")
            return False

        try:
            self._servicio.eliminar_movimiento(fila.id)
        except (LookupError, ValueError) as exc:
            self.mensaje.emit(str(exc))
            return False

        self.recargar()
        self.cambio.emit()
        self.mensaje.emit(f"Registro «{referencia}» eliminado.")
        return True


class PanelSistema(QWidget):
    """Identidad y conexión: lo que se eligió al instalar, editable después.

    El instalador pregunta una vez; esto permite cambiarlo sin tocar archivos ni
    reinstalar. Nunca muestra la contraseña: el resumen dice servidor, base y
    usuario, que es lo que hace falta para reconocer la conexión.
    """

    configuracion_cambiada = Signal()
    mensaje = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._valores: dict[str, QLabel] = {}

        titulo = QLabel("Sistema")
        titulo.setObjectName("TituloVista")
        detalle = QLabel(
            "La identidad que se ve en la ventana y la conexión a la base de datos. "
            "Se pregunta al instalar y se puede cambiar desde acá."
        )
        detalle.setObjectName("SubtituloVista")
        detalle.setWordWrap(True)

        self.previa = QLabel()
        self.previa.setFixedHeight(64)
        self.previa.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

        tarjeta = QFrame()
        tarjeta.setObjectName("Tarjeta")
        columna_tarjeta = QVBoxLayout(tarjeta)
        columna_tarjeta.setContentsMargins(16, 14, 16, 16)
        columna_tarjeta.setSpacing(8)
        for clave, etiqueta in (
            ("nombre", "Nombre visible"),
            ("organizacion", "Organización"),
            ("descripcion", "Descripción"),
            ("servidor", "Servidor"),
            ("base", "Base de datos"),
            ("usuario", "Usuario de base de datos"),
        ):
            fila = QHBoxLayout()
            fila.setSpacing(10)
            nombre = QLabel(etiqueta)
            nombre.setObjectName("ClaveDetalle")
            nombre.setFixedWidth(190)
            valor = QLabel("—")
            valor.setObjectName("ValorDetalle")
            valor.setWordWrap(True)
            fila.addWidget(nombre)
            fila.addWidget(valor, 1)
            columna_tarjeta.addLayout(fila)
            self._valores[clave] = valor
        columna_tarjeta.addSpacing(4)
        columna_tarjeta.addWidget(self.previa)

        self.boton_cambiar = QPushButton("Cambiar configuración…")
        self.boton_cambiar.setObjectName("BotonPrimario")
        self.boton_cambiar.setIcon(icono("ajustes", COLORES["blanco"]))
        self.boton_cambiar.clicked.connect(self.abrir_configuracion)

        self.aviso = QLabel()
        self.aviso.setObjectName("AvisoRevision")
        self.aviso.setWordWrap(True)
        self.aviso.hide()

        acciones = QHBoxLayout()
        acciones.addWidget(self.boton_cambiar)
        acciones.addStretch(1)

        caja = QVBoxLayout(self)
        caja.setContentsMargins(18, 16, 18, 16)
        caja.setSpacing(10)
        caja.addWidget(titulo)
        caja.addWidget(detalle)
        caja.addSpacing(4)
        caja.addWidget(tarjeta)
        caja.addWidget(self.aviso)
        caja.addStretch(1)
        caja.addLayout(acciones)

        self.recargar()

    def recargar(self) -> None:
        configuracion = cargar_configuracion(refrescar=True)
        self._valores["nombre"].setText(configuracion.nombre or "sin configurar")
        self._valores["organizacion"].setText(configuracion.organizacion or "—")
        self._valores["descripcion"].setText(configuracion.descripcion or "—")

        campos = (
            campos_desde_url(configuracion.database_url)
            if configuracion.database_url
            else {}
        )
        if campos:
            self._valores["servidor"].setText(
                f"{campos['host']}:{campos['puerto']}"
            )
            self._valores["base"].setText(str(campos.get("base") or "—"))
            self._valores["usuario"].setText(str(campos.get("usuario") or "—"))
        else:
            for clave in ("servidor", "base", "usuario"):
                self._valores[clave].setText("sin configurar")

        if configuracion.logo is not None and configuracion.logo.is_file():
            pixmap = QPixmap(str(configuracion.logo))
            self.previa.setPixmap(
                pixmap.scaledToHeight(56) if not pixmap.isNull() else QPixmap()
            )
        else:
            self.previa.setText("Logo genérico del programa")

    def abrir_configuracion(self) -> bool:
        from taller.ui.views.configuracion_inicial import ConfiguracionInicialDialog

        actual = cargar_configuracion(refrescar=True)
        dialogo = ConfiguracionInicialDialog(self, inicial=actual if actual.nombre else None)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return False
        self.recargar()
        self.aviso.setText(
            "Guardado. El nombre y el logo nuevos se ven al reiniciar el programa; "
            "la conexión ya está activa."
        )
        self.aviso.show()
        self.configuracion_cambiada.emit()
        return True


class PanelHistorial(QWidget):
    """Quién cambió qué en los catálogos.

    Antes de esta pantalla, desactivar un técnico no dejaba rastro en ninguna
    parte: aparecían inactivos y no había forma de saber quién ni cuándo.
    """

    def __init__(self, servicio: ServicioTaller, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._servicio = servicio
        self._modelo = HistorialTableModel()

        titulo = QLabel("Historial de catálogos")
        titulo.setObjectName("TituloVista")
        detalle = QLabel(
            "Cada alta, renombrado, activación, desactivación o fusión de un área, "
            "un tipo de equipo o un técnico, con quién lo hizo."
        )
        detalle.setObjectName("SubtituloVista")
        detalle.setWordWrap(True)

        self.tabla = QTableView()
        self.tabla.setModel(self._modelo)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(26)
        cabecera = self.tabla.horizontalHeader()
        cabecera.setStretchLastSection(True)
        cabecera.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for columna in (1, 2, 3, 4, 5):
            cabecera.setSectionResizeMode(columna, QHeaderView.ResizeMode.Stretch)

        self.boton_refrescar = QPushButton("Actualizar")
        self.boton_refrescar.setIcon(icono("buscar", COLORES["gris-700"]))
        self.boton_refrescar.clicked.connect(self.recargar)

        self.vacio = QLabel("Todavía no hay cambios de catálogo registrados.")
        self.vacio.setObjectName("SubtituloVista")

        acciones = QHBoxLayout()
        acciones.addWidget(self.vacio)
        acciones.addStretch(1)
        acciones.addWidget(self.boton_refrescar)

        caja = QVBoxLayout(self)
        caja.setContentsMargins(18, 16, 18, 16)
        caja.setSpacing(10)
        caja.addWidget(titulo)
        caja.addWidget(detalle)
        caja.addWidget(self.tabla, 1)
        caja.addLayout(acciones)

        self.recargar()

    def recargar(self) -> None:
        filas = self._servicio.historial_catalogo()
        self._modelo.reemplazar(filas)
        self.vacio.setVisible(not filas)


class PanelUsuarios(QWidget):
    """Cuentas de la aplicación: quién puede entrar y quién administra.

    Solo la ve un administrador, y la pestaña ni siquiera se crea para los demás:
    esconder un botón no es lo mismo que no ofrecerlo.
    """

    cambio = Signal()
    mensaje = Signal(str)

    def __init__(self, servicio: ServicioTaller, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._servicio = servicio
        self._modelo = UsuariosTableModel()

        titulo = QLabel("Usuarios")
        titulo.setObjectName("TituloVista")
        detalle = QLabel(
            "Cada cambio queda registrado a nombre de quien entró con su contraseña. "
            "Un usuario inactivo no puede entrar, pero conserva su historial."
        )
        detalle.setObjectName("SubtituloVista")
        detalle.setWordWrap(True)

        self.tabla = QTableView()
        self.tabla.setModel(self._modelo)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setAlternatingRowColors(True)
        cabecera = self.tabla.horizontalHeader()
        cabecera.setStretchLastSection(True)
        cabecera.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tabla.selectionModel().selectionChanged.connect(self._actualizar_botones)
        self.tabla.doubleClicked.connect(lambda *_: self.cambiar_clave())

        self.boton_nuevo = QPushButton("Nuevo usuario")
        self.boton_nuevo.setObjectName("BotonPrimario")
        self.boton_nuevo.setIcon(icono("nuevo", COLORES["blanco"]))
        self.boton_nuevo.clicked.connect(self.nuevo)

        self.boton_clave = QPushButton("Cambiar contraseña…")
        self.boton_clave.setIcon(icono("editar", COLORES["gris-700"]))
        self.boton_clave.clicked.connect(self.cambiar_clave)

        self.boton_estado = QPushButton("Desactivar")
        self.boton_estado.clicked.connect(self.alternar)

        self.boton_admin = QPushButton("Hacer administrador")
        self.boton_admin.clicked.connect(self.alternar_admin)

        acciones = QHBoxLayout()
        acciones.setSpacing(8)
        for boton in (
            self.boton_nuevo,
            self.boton_clave,
            self.boton_estado,
            self.boton_admin,
        ):
            acciones.addWidget(boton)
        acciones.addStretch(1)

        caja = QVBoxLayout(self)
        caja.setContentsMargins(18, 16, 18, 16)
        caja.setSpacing(10)
        caja.addWidget(titulo)
        caja.addWidget(detalle)
        caja.addWidget(self.tabla, 1)
        caja.addLayout(acciones)

        self.recargar()

    # ------------------------------------------------------------------ estado

    def recargar(self) -> None:
        self._modelo.reemplazar(self._servicio.listar_usuarios())
        self._actualizar_botones()

    def seleccionado(self):
        indices = self.tabla.selectionModel().selectedRows()
        if not indices:
            return None
        return self._modelo.fila(indices[0].row())

    def _actualizar_botones(self, *_args: object) -> None:
        cuenta = self.seleccionado()
        hay = cuenta is not None
        for boton in (self.boton_clave, self.boton_estado, self.boton_admin):
            boton.setEnabled(hay)
        if cuenta is None:
            self.boton_estado.setText("Desactivar")
            self.boton_admin.setText("Hacer administrador")
            return
        self.boton_estado.setText("Activar" if not cuenta.activo else "Desactivar")
        # A uno mismo no se le quita la cuenta: se quedaría afuera del sistema.
        propio = cuenta.nombre == self._servicio.usuario
        self.boton_estado.setEnabled(hay and not propio)
        self.boton_admin.setText(
            "Quitar administrador" if cuenta.es_admin else "Hacer administrador"
        )

    # ------------------------------------------------------------------ acción

    def nuevo(self) -> None:
        from taller.ui.views.ingreso_view import DialogoClave

        dialogo = DialogoClave(
            self,
            titulo="Nuevo usuario",
            detalle="La persona entra con este nombre y esta contraseña.",
        )
        if dialogo.exec() != QDialog.DialogCode.Accepted or dialogo.clave is None:
            return
        try:
            self._servicio.crear_usuario(
                dialogo.nombre.text().strip(), dialogo.clave
            )
        except ValueError as error:
            self._avisar(str(error))
            return
        self.recargar()
        self.cambio.emit()
        self.mensaje.emit("Usuario creado.")

    def cambiar_clave(self) -> None:
        from taller.ui.views.ingreso_view import DialogoClave

        cuenta = self.seleccionado()
        if cuenta is None:
            return
        dialogo = DialogoClave(
            self,
            titulo="Cambiar contraseña",
            detalle=f"Contraseña nueva para {cuenta.nombre}.",
            nombre=cuenta.nombre,
        )
        if dialogo.exec() != QDialog.DialogCode.Accepted or dialogo.clave is None:
            return
        try:
            self._servicio.cambiar_clave_usuario(cuenta.id, dialogo.clave)
        except ValueError as error:
            self._avisar(str(error))
            return
        self.mensaje.emit(f"Contraseña de {cuenta.nombre} cambiada.")

    def alternar(self) -> bool:
        cuenta = self.seleccionado()
        if cuenta is None:
            return False
        accion = "activar" if not cuenta.activo else "desactivar"
        if not self._confirmar(f"¿{accion.capitalize()} a {cuenta.nombre}?"):
            return False
        try:
            self._servicio.alternar_usuario(cuenta.id)
        except ValueError as error:
            self._avisar(str(error))
            return False
        self.recargar()
        self.cambio.emit()
        return True

    def alternar_admin(self) -> bool:
        cuenta = self.seleccionado()
        if cuenta is None:
            return False
        try:
            self._servicio.asignar_administrador(cuenta.id, es_admin=not cuenta.es_admin)
        except ValueError as error:
            self._avisar(str(error))
            return False
        self.recargar()
        self.cambio.emit()
        return True

    def _confirmar(self, pregunta: str) -> bool:
        respuesta = QMessageBox.question(
            self,
            "Confirmar",
            pregunta,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return respuesta == QMessageBox.StandardButton.Yes

    def _avisar(self, texto: str) -> None:
        QMessageBox.warning(self, "No se pudo", texto)
        self.mensaje.emit(texto)


class ConfiguracionView(QWidget):
    """The three catalogs, one tab each."""

    catalogo_cambiado = Signal()
    configuracion_cambiada = Signal()
    mensaje = Signal(str)

    def __init__(self, servicio: ServicioTaller, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._servicio = servicio

        self.pestanas = QTabWidget()
        self.paneles: dict[str, PanelCatalogo] = {}
        for dimension, (titulo, descripcion) in ETIQUETAS.items():
            panel = PanelCatalogo(servicio, dimension, titulo, descripcion)
            panel.cambio.connect(self.catalogo_cambiado.emit)
            self.paneles[dimension] = panel
            self.pestanas.addTab(panel, titulo)

        self.administracion = PanelAdministracion(servicio)
        self.administracion.cambio.connect(self.catalogo_cambiado.emit)
        self.administracion.mensaje.connect(self.mensaje.emit)
        self.pestanas.addTab(self.administracion, "Administración")

        self.sistema = PanelSistema()
        self.sistema.configuracion_cambiada.connect(self.configuracion_cambiada.emit)
        self.pestanas.addTab(self.sistema, "Sistema")

        self.historial = PanelHistorial(servicio)
        self.pestanas.addTab(self.historial, "Historial")

        # El panel ni se construye si quien entró no administra: no es un botón
        # escondido, es una capacidad que no está en la pantalla.
        self.usuarios = PanelUsuarios(servicio) if servicio.es_admin else None
        if self.usuarios is not None:
            self.usuarios.cambio.connect(self.catalogo_cambiado.emit)
            self.usuarios.mensaje.connect(self.mensaje.emit)
            self.pestanas.addTab(self.usuarios, "Usuarios")

        caja = QVBoxLayout(self)
        caja.setContentsMargins(20, 18, 20, 18)
        caja.setSpacing(10)
        caja.addWidget(self.pestanas)

    def recargar(self) -> None:
        for panel in self.paneles.values():
            panel.recargar()
        self.administracion.recargar()
        self.sistema.recargar()
        if self.usuarios is not None:
            self.usuarios.recargar()
        self.historial.recargar()

    def panel(self, dimension: str) -> PanelCatalogo:
        return self.paneles[dimension]
