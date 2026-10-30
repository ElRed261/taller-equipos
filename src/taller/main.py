"""Punto de entrada de la aplicación.

Dos guardas antes de mostrar la ventana, porque es un sistema en red:

1. **Sin usuario no se entra.** La auditoría atribuye cada edición a un nombre; un
   sistema que no sabe quién escribe no puede auditar nada. El nombre se pide o
   viene de ``TALLER_USUARIO``, nunca de ``getpass``.
2. **Sin base no se entra con un traceback.** Si el servidor está caído aparece un
   diálogo con el motivo y la opción de reintentar.

Uso:
    uv run python -m taller.main
"""

from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QInputDialog, QLineEdit, QMessageBox

from taller.config.settings import get_settings
from taller.servicios import ServicioTaller
from taller.ui.main_window import VentanaPrincipal
from taller.ui.tema import RUTA_LOGO, hoja_de_estilo


def resolver_usuario(settings_usuario: str) -> str | None:
    """Ask for the application user. Returns ``None`` when the user cancels."""
    if settings_usuario.strip():
        return settings_usuario.strip()
    nombre, aceptado = QInputDialog.getText(
        None,
        "Taller de equipos",
        "¿Quién está usando el sistema?\n(Cada edición queda registrada a tu nombre.)",
        QLineEdit.EchoMode.Normal,
    )
    if not aceptado or not nombre.strip():
        return None
    return nombre.strip()


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
    app.setApplicationName("Taller de equipos")
    app.setOrganizationName("Taller de equipos")
    app.setWindowIcon(QIcon(str(RUTA_LOGO)))
    app.setStyleSheet(hoja_de_estilo())

    usuario = resolver_usuario(get_settings().usuario)
    if usuario is None:
        return 1

    servicio = ServicioTaller(usuario)
    if not conectar(servicio):
        return 1

    ventana = VentanaPrincipal(servicio)
    ventana.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
