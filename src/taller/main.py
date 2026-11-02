"""Punto de entrada de la aplicación.

Tres guardas antes de mostrar la ventana, porque es un sistema en red:

1. **Sin configuración no se entra.** La primera vez se piden la marca, la
   conexión y se crean las tablas desde el asistente.
2. **Sin cuenta no se entra**, salvo que el ingreso esté desactivado en la
   configuración. Con el ingreso encendido, la auditoría atribuye cada edición a una
   cuenta con contraseña verificada contra la base, y no hay forma de elegir el
   nombre por fuera. Apagado, se entra con la cuenta por defecto y la ventana lo
   dice en la barra inferior: una auditoría sin contraseña tiene que verse, no
   parecer lo mismo que una con contraseña.
3. **Sin base no se entra con un traceback.** Si el servidor está caído aparece un
   diálogo con el motivo y la opción de reintentar.

Uso:
    uv run python -m taller.main
"""

from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from taller.arranque import (
    configuracion_completa,
    hay_configuracion_externa,
    ingreso_obligatorio,
    preparar_base,
    reiniciar_cache,
    usuario_por_defecto,
)
from taller.config.settings import get_settings
from taller.database.connection import reset_engine
from taller.servicios import ServicioTaller
from taller.ui.main_window import VentanaPrincipal
from taller.ui.marca import cargar_marca
from taller.ui.tema import hoja_de_estilo
from taller.ui.views.configuracion_inicial import ConfiguracionInicialDialog
from taller.ui.views.ingreso_view import DialogoIngreso, DialogoPrimerAdministrador


def cuenta_de_entrada_directa() -> tuple[str, bool] | None:
    """The account used when the login is disabled, or ``None`` if it cannot be resolved.

    Sin una cuenta clara no se inventa un nombre: se cae al ingreso normal, que es
    lo único que deja la auditoría en pie.
    """
    pedida = usuario_por_defecto()
    cuenta = ServicioTaller.cuenta_sin_contrasena(pedida)
    if cuenta is None:
        return None
    return cuenta.nombre, cuenta.es_admin


def autenticar() -> tuple[str, bool] | None:
    """Get the account that will own this session, or ``None`` if nobody entered.

    Sin administrador no hay quién dé de alta a los demás, así que la primera vez
    se crea uno. Si la base no responde, se ofrece reintentar en vez de terminar
    con un error que no dice nada.
    """
    if not ingreso_obligatorio():
        directa = cuenta_de_entrada_directa()
        if directa is not None:
            return directa
        # Sin cuenta por defecto no hay a quién atribuir los cambios: se pregunta.

    while True:
        try:
            hay_administrador = ServicioTaller.hay_administrador()
            existentes = (
                [] if hay_administrador
                else [cuenta.nombre for cuenta in ServicioTaller.cuentas_existentes()]
            )
        except Exception as error:  # noqa: BLE001 - se muestra el motivo
            respuesta = QMessageBox.critical(
                None,
                "Sin conexión con el servidor",
                f"No se pudo consultar la base de datos.\n\n{error}\n\n"
                "Avisá al administrador o reintentá cuando el servidor esté disponible.",
                QMessageBox.StandardButton.Retry | QMessageBox.StandardButton.Close,
                QMessageBox.StandardButton.Retry,
            )
            if respuesta != QMessageBox.StandardButton.Retry:
                return None
            continue

        if not hay_administrador:
            primero = DialogoPrimerAdministrador(existentes=existentes)
            if primero.exec() != QDialog.DialogCode.Accepted or not primero.usuario:
                return None
            return primero.usuario, True

        ingreso = DialogoIngreso()
        if ingreso.exec() != QDialog.DialogCode.Accepted or not ingreso.usuario:
            return None
        return ingreso.usuario, ingreso.es_admin


def conectar(servicio: ServicioTaller) -> bool:
    """Retry loop around the connectivity check."""
    while True:
        ok, detalle = servicio.conexion_ok()
        if ok:
            return True
        respuesta = QMessageBox.critical(
            None,
            "Sin conexión con el servidor",
            f"No se pudo conectar con la base de datos.\n\n{detalle}\n\n"
            "Avisá al administrador o reintentá cuando el servidor esté disponible.",
            QMessageBox.StandardButton.Retry | QMessageBox.StandardButton.Close,
            QMessageBox.StandardButton.Retry,
        )
        if respuesta != QMessageBox.StandardButton.Retry:
            return False


def main(argv: list[str] | None = None) -> int:
    argumentos = argv if argv is not None else sys.argv
    # --version se responde antes de crear la aplicación: sirve para verificar un
    # binario empaquetado sin abrir una ventana (y sin necesitar pantalla).
    if "--version" in argumentos:
        import PySide6

        from taller import __version__

        print(
            f"taller-equipos {__version__} · PySide6 {PySide6.__version__} · "
            f"Python {sys.version.split()[0]}"
        )
        return 0

    app = QApplication(argumentos)
    app.setStyleSheet(hoja_de_estilo())

    # Primera vez: marca, conexión y creación de las tablas. Sin esto no hay nada
    # que mostrar, así que va antes que cualquier otra guarda.
    if not configuracion_completa() and not hay_configuracion_externa():
        asistente = ConfiguracionInicialDialog()
        if asistente.exec() != QDialog.DialogCode.Accepted:
            return 1
        reiniciar_cache()
        reset_engine()

    marca = cargar_marca()
    app.setApplicationName(marca.nombre)
    app.setOrganizationName(marca.organizacion)
    app.setWindowIcon(QIcon(str(marca.logo)))

    # La base primero: sin tablas no hay usuarios que consultar. Si es la primera
    # vez, esto las crea; si ya existía, solo se conecta.
    lista, motivo = preparar_base(get_settings().database_url)
    if not lista:
        QMessageBox.critical(None, "No se pudo preparar la base", motivo)
        return 1

    cuenta = autenticar()
    if cuenta is None:
        return 0  # cancelar no es un error: la persona decidió no entrar

    usuario, es_admin = cuenta
    servicio = ServicioTaller(usuario, es_admin=es_admin)
    if not conectar(servicio):
        return 1

    ventana = VentanaPrincipal(servicio)
    ventana.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
