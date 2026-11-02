"""El instalador gráfico: qué detecta, qué copia y qué quita.

Se prueba la lógica, no la ventana: la ventana solo muestra estas respuestas. Todo
corre contra una carpeta temporal, así que no toca la instalación real ni la
configuración de quien ejecuta las pruebas.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from taller import instalador


@pytest.fixture
def programa_falso(tmp_path: Path, monkeypatch) -> Path:
    """Una carpeta que parece una instalación: binario adentro."""
    origen = tmp_path / "origen"
    origen.mkdir()
    (origen / instalador.NOMBRE_BINARIO).write_text("#!/bin/sh\n", encoding="utf-8")
    (origen / "version.json").write_text('{"version": "9.9.9"}', encoding="utf-8")
    monkeypatch.setattr(instalador, "raiz_del_programa", lambda: origen)
    return origen


@pytest.fixture
def casa_temporal(tmp_path: Path, monkeypatch) -> Path:
    """Todo apunta a una carpeta temporal: ninguna prueba toca la máquina real.

    Se reemplazan también ``destino_usuario`` y ``destino_sistema``, no solo HOME:
    con HOME alcanzaba para la instalación de usuario, pero ``destino_sistema`` es
    ``/usr/local`` de verdad y una prueba de desinstalación borró una instalación
    real por no aislarlo.
    """
    casa = tmp_path / "casa"
    casa.mkdir()
    monkeypatch.setenv("HOME", str(casa))
    monkeypatch.setenv("XDG_DATA_HOME", str(casa / ".local" / "share"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(instalador, "carpeta_configuracion", lambda: casa / "config")
    monkeypatch.setattr(
        instalador, "destino_usuario", lambda: casa / ".local" / "lib" / "taller-equipos"
    )
    monkeypatch.setattr(
        instalador, "destino_sistema", lambda: casa / "sistema" / "lib" / "taller-equipos"
    )
    return casa


class TestDeteccion:
    def test_sin_nada_instalado_no_devuelve_nada(self, casa_temporal: Path) -> None:
        """Si el fixture fallara en aislar, acá aparecería la instalación real."""
        assert instalador.detectar() == []

    def test_encuentra_una_instalacion_de_usuario(
        self, casa_temporal: Path, monkeypatch
    ) -> None:
        destino = instalador.destino_usuario()
        destino.mkdir(parents=True)
        (destino / instalador.NOMBRE_BINARIO).write_text("x", encoding="utf-8")

        encontradas = instalador.detectar()
        assert len(encontradas) == 1
        assert encontradas[0].ruta == destino

    def test_una_carpeta_sin_binario_no_cuenta(
        self, casa_temporal: Path
    ) -> None:
        # Restos de una instalación a medio borrar no son una instalación.
        instalador.destino_usuario().mkdir(parents=True)
        assert instalador.detectar() == []


class TestInstalacion:
    def test_copia_el_programa_y_crea_el_lanzador(
        self, programa_falso: Path, casa_temporal: Path
    ) -> None:
        resultado = instalador.instalar()

        assert resultado.ok, resultado.mensaje
        destino = instalador.destino_usuario()
        assert (destino / instalador.NOMBRE_BINARIO).is_file()
        lanzador = casa_temporal / ".local" / "bin" / "taller-equipos"
        assert lanzador.is_file()
        assert os.access(lanzador, os.X_OK)
        assert (destino / "version.json").is_file()

    def test_reinstalar_reemplaza_sin_dejar_restos(
        self, programa_falso: Path, casa_temporal: Path
    ) -> None:
        assert instalador.instalar().ok
        (instalador.destino_usuario() / "basura.txt").write_text("x", encoding="utf-8")
        assert instalador.instalar().ok
        # La copia nueva no arrastra lo que había en la anterior.
        assert not (instalador.destino_usuario() / "basura.txt").exists()

    def test_no_instala_sobre_si_mismo(
        self, programa_falso: Path, casa_temporal: Path, monkeypatch
    ) -> None:
        monkeypatch.setattr(instalador, "destino_usuario", lambda: programa_falso)
        resultado = instalador.instalar()
        assert resultado.ok is False
        assert "corriendo" in resultado.mensaje


class TestDesinstalacion:
    def test_quita_el_programa_y_respeta_la_configuracion(
        self, programa_falso: Path, casa_temporal: Path
    ) -> None:
        assert instalador.instalar().ok
        configuracion = instalador.carpeta_configuracion()
        configuracion.mkdir(parents=True)
        (configuracion / "config.json").write_text("{}", encoding="utf-8")

        resultado = instalador.desinstalar()

        assert resultado.ok, resultado.mensaje
        assert not instalador.destino_usuario().exists()
        assert not (casa_temporal / ".local" / "bin" / "taller-equipos").exists()
        assert configuracion.is_dir(), "borró la configuración sin que se lo pidieran"
        assert any("La configuración sigue" in d for d in resultado.detalles)

    def test_con_configuracion_la_borra(
        self, programa_falso: Path, casa_temporal: Path
    ) -> None:
        assert instalador.instalar().ok
        configuracion = instalador.carpeta_configuracion()
        configuracion.mkdir(parents=True)

        resultado = instalador.desinstalar(borrar_configuracion=True)

        assert resultado.ok
        assert not configuracion.exists()

    def test_sin_instalacion_lo_dice(self, casa_temporal: Path) -> None:
        resultado = instalador.desinstalar()
        assert resultado.ok is False
        assert "No hay ninguna instalación" in resultado.mensaje

    def test_siempre_avisa_que_la_base_sigue_ahi(
        self, programa_falso: Path, casa_temporal: Path
    ) -> None:
        assert instalador.instalar().ok
        resultado = instalador.desinstalar()
        assert any("base de datos" in d.lower() for d in resultado.detalles)


class TestWizardCompleto:
    """El asistente de instalación incluye copiar el programa.

    Una sola ventana hace las dos cosas: configurar la aplicación y dejarla
    instalada. Sin la casilla conectada, el usuario tiene que comandos aparte.
    """

    def test_la_casilla_existe_y_dice_el_destino(self, qtbot: object) -> None:
        from taller.ui.views.configuracion_inicial import ConfiguracionInicialDialog

        dialogo = ConfiguracionInicialDialog()
        qtbot.addWidget(dialogo)  # type: ignore[attr-defined]
        assert dialogo.copiar_programa.isChecked() is False
        assert str(dialogo.detalle_copia.text()).endswith(
            "crea el acceso directo."
        )

    def test_guardar_con_la_casilla_instala_de_verdad(
        self, qtbot: object, monkeypatch, tmp_path: Path, casa_temporal, programa_falso
    ) -> None:
        from PySide6.QtWidgets import QDialog

        import taller.arranque as arranque
        from taller.ui.views.configuracion_inicial import ConfiguracionInicialDialog

        monkeypatch.setattr(
            arranque, "ruta_configuracion", lambda: tmp_path / "config.json"
        )
        dialogo = ConfiguracionInicialDialog()
        qtbot.addWidget(dialogo)  # type: ignore[attr-defined]
        dialogo.copiar_programa.setChecked(True)
        dialogo._conexion_ok = True
        dialogo.nombre.setText("Prueba")

        assert dialogo.guardar() is True
        assert dialogo.result() == QDialog.DialogCode.Accepted
        # Con la casilla marcada, el programa quedó copiado al destino del sandbox.
        copiado = instalador.destino_usuario() / instalador.NOMBRE_BINARIO
        assert copiado.is_file(), copiado
        # Y el acceso directo apunta a la copia, no al original.
        lanzador = casa_temporal / ".local" / "bin" / "taller-equipos"
        assert lanzador.exists()
        assert str(instalador.destino_usuario()) in lanzador.read_text(encoding="utf-8")
