"""Arranque: configuración persistente y asistente de primera ejecución.

Lo que se prueba acá es lo que hace que el programa se pueda instalar sin editar
archivos a mano: que la configuración sobreviva, que un archivo roto no rompa la
aplicación, y que el asistente no deje guardar nada sin haber probado la conexión.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from taller.arranque import (
    ConfiguracionArranque,
    cargar_configuracion,
    carpeta_configuracion,
    carpeta_migraciones,
    configuracion_completa,
    copiar_logo,
    guardar_configuracion,
    reiniciar_cache,
    ruta_configuracion,
    url_desde_campos,
)
from taller.ui.views.configuracion_inicial import ConfiguracionInicialDialog


@pytest.fixture
def carpeta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("TALLER_CONFIG_DIR", str(tmp_path / "config"))
    reiniciar_cache()
    yield tmp_path / "config"
    reiniciar_cache()


class TestConfiguracionPersistente:
    def test_sin_archivo_no_esta_configurada(self, carpeta: Path) -> None:
        assert configuracion_completa() is False
        assert cargar_configuracion().database_url == ""

    def test_guardar_y_volver_a_leer(self, carpeta: Path) -> None:
        guardar_configuracion(
            ConfiguracionArranque(
                database_url="postgresql+psycopg://u:p@localhost:5432/taller",
                nombre="Mi Taller",
                organizacion="Mi Org",
                descripcion="Equipos",
            )
        )
        reiniciar_cache()
        leida = cargar_configuracion()
        assert leida.database_url.endswith("/taller")
        assert leida.nombre == "Mi Taller"
        assert leida.organizacion == "Mi Org"
        assert configuracion_completa() is True

    def test_un_archivo_roto_no_rompe_la_aplicacion(self, carpeta: Path) -> None:
        carpeta.mkdir(parents=True, exist_ok=True)
        ruta_configuracion().write_text("{ esto no es json", encoding="utf-8")
        reiniciar_cache()
        assert cargar_configuracion().database_url == ""
        assert configuracion_completa() is False

    def test_un_logo_borrado_se_ignora(self, carpeta: Path) -> None:
        carpeta.mkdir(parents=True, exist_ok=True)
        ruta_configuracion().write_text(
            json.dumps(
                {
                    "database_url": "postgresql+psycopg://u:p@localhost/t",
                    "branding": {"nombre": "X", "logo": str(carpeta / "no-existe.png")},
                }
            ),
            encoding="utf-8",
        )
        reiniciar_cache()
        assert cargar_configuracion().logo is None

    def test_el_logo_elegido_se_copia_a_la_carpeta_de_configuracion(
        self, carpeta: Path, tmp_path: Path
    ) -> None:
        original = tmp_path / "elegido.png"
        original.write_bytes(b"\x89PNG\r\n\x1a\n")
        copiado = copiar_logo(original)
        assert copiado.is_file()
        assert copiado.parent == carpeta_configuracion()
        assert copiado != original

    def test_guarda_la_configuracion_una_sola_vez(self, carpeta: Path) -> None:
        guardar_configuracion(ConfiguracionArranque(database_url="a", nombre="A"))
        guardar_configuracion(ConfiguracionArranque(database_url="b", nombre="B"))
        reiniciar_cache()
        assert cargar_configuracion().nombre == "B"


class TestUrl:
    def test_arma_la_url_desde_los_campos(self) -> None:
        url = url_desde_campos("mi-servidor", 5433, "taller", "secreta", "taller_dev")
        assert url == "postgresql+psycopg://taller:secreta@mi-servidor:5433/taller_dev"

    def test_una_contrasena_con_simbolos_no_rompe_la_url(self) -> None:
        url = url_desde_campos("localhost", 5432, "u", "a@b:c/d", "t")
        assert "a%40b%3Ac%2Fd" in url

    def test_el_puerto_puede_venir_como_texto(self) -> None:
        assert ":5432/" in url_desde_campos("h", "5432", "u", "p", "b")

    def test_los_vacios_caen_en_valores_razonables(self) -> None:
        url = url_desde_campos("", 5432, "u", "p", "")
        assert "@localhost:5432/taller" in url


class TestMigraciones:
    def test_encuentra_el_directorio_de_migraciones(self) -> None:
        carpeta = carpeta_migraciones()
        assert (carpeta / "env.py").is_file()
        assert (carpeta / "versions").is_dir()


class TestAsistente:
    def _asistente(
        self, qtbot: object, *resultados: tuple[bool, str]
    ) -> tuple[ConfiguracionInicialDialog, list[str], list[str]]:
        conexiones: list[str] = []
        migraciones: list[str] = []

        def verificador(url: str) -> tuple[bool, str]:
            conexiones.append(url)
            return resultados[min(len(conexiones) - 1, len(resultados) - 1)]

        def migrador(url: str) -> None:
            migraciones.append(url)

        dialogo = ConfiguracionInicialDialog(verificador=verificador, migrador=migrador)
        qtbot.addWidget(dialogo)  # type: ignore[attr-defined]
        return dialogo, conexiones, migraciones

    def test_arranca_sin_permiso_de_guardar(self, qtbot: object, carpeta: Path) -> None:
        dialogo, _conexiones, _migraciones = self._asistente(qtbot, (True, "ok"))
        assert not dialogo.boton_guardar.isEnabled()
        assert not dialogo.boton_tablas.isEnabled()

    def test_una_conexion_fallida_muestra_el_motivo(
        self, qtbot: object, carpeta: Path
    ) -> None:
        dialogo, conexiones, _migraciones = self._asistente(
            qtbot, (False, "connection refused")
        )
        assert dialogo.probar() is False
        assert conexiones
        assert not dialogo.error.isHidden()
        assert "connection refused" in dialogo.error.text()
        assert not dialogo.boton_guardar.isEnabled()

    def test_una_conexion_correcta_habilita_los_pasos(
        self, qtbot: object, carpeta: Path
    ) -> None:
        dialogo, conexiones, _migraciones = self._asistente(qtbot, (True, "ok"))
        assert dialogo.probar() is True
        assert conexiones[0].startswith("postgresql+psycopg://")
        assert dialogo.boton_guardar.isEnabled()
        assert dialogo.boton_tablas.isEnabled()

    def test_crear_tablas_sin_conexion_no_llama_al_migrador(
        self, qtbot: object, carpeta: Path
    ) -> None:
        dialogo, _conexiones, migraciones = self._asistente(qtbot, (True, "ok"))
        assert dialogo.crear_tablas() is False
        assert migraciones == []

    def test_crear_tablas_usa_la_url_probada(
        self, qtbot: object, carpeta: Path
    ) -> None:
        dialogo, _conexiones, migraciones = self._asistente(qtbot, (True, "ok"))
        dialogo.probar()
        assert dialogo.crear_tablas() is True
        assert migraciones == [dialogo.url()]

    def test_un_error_al_migrar_se_muestra(self, qtbot: object, carpeta: Path) -> None:
        def migrador(_url: str) -> None:
            raise RuntimeError("no hay permisos")

        dialogo = ConfiguracionInicialDialog(
            verificador=lambda _url: (True, "ok"), migrador=migrador
        )
        qtbot.addWidget(dialogo)  # type: ignore[attr-defined]
        dialogo.probar()
        assert dialogo.crear_tablas() is False
        assert "no hay permisos" in dialogo.error.text()

    def test_guardar_sin_conexion_no_escribe_nada(
        self, qtbot: object, carpeta: Path
    ) -> None:
        dialogo, _conexiones, _migraciones = self._asistente(qtbot, (True, "ok"))
        assert dialogo.guardar() is False
        assert not ruta_configuracion().is_file()

    def test_guardar_con_conexion_escribe_la_configuracion(
        self, qtbot: object, carpeta: Path, tmp_path: Path
    ) -> None:
        logo = tmp_path / "logo.png"
        logo.write_bytes(b"\x89PNG\r\n\x1a\n")

        dialogo, _conexiones, _migraciones = self._asistente(qtbot, (True, "ok"))
        dialogo.nombre.setText("Taller Central")
        dialogo.organizacion.setText("Org")
        dialogo._logo_elegido = logo
        dialogo.probar()

        assert dialogo.guardar() is True
        reiniciar_cache()
        guardada = cargar_configuracion()
        assert guardada.nombre == "Taller Central"
        assert guardada.logo is not None and guardada.logo.is_file()

    def test_un_nombre_vacio_no_se_guarda(self, qtbot: object, carpeta: Path) -> None:
        dialogo, _conexiones, _migraciones = self._asistente(qtbot, (True, "ok"))
        dialogo.nombre.setText("   ")
        dialogo.probar()
        assert dialogo.guardar() is False
        assert "vacío" in dialogo.error.text()


class TestConfiguracionExterna:
    """El asistente no debe aparecer si la conexión ya está definida."""

    def test_sin_nada_configurado_no_hay_configuracion_externa(
        self, carpeta: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from taller.arranque import hay_configuracion_externa

        monkeypatch.delenv("TALLER_DATABASE_URL", raising=False)
        monkeypatch.chdir(tmp_path)
        # Sin esto, el .env del propio repositorio contaría como configuración.
        monkeypatch.setenv("TALLER_ENV_FILE", str(tmp_path / "nada.env"))
        assert hay_configuracion_externa() is False

    def test_la_variable_de_entorno_cuenta_como_configuracion(
        self, carpeta: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from taller.arranque import hay_configuracion_externa

        monkeypatch.setenv("TALLER_DATABASE_URL", "postgresql+psycopg://x@y/z")
        assert hay_configuracion_externa() is True

    def test_un_dot_env_con_la_url_cuenta_como_configuracion(
        self, carpeta: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from taller.arranque import hay_configuracion_externa

        monkeypatch.delenv("TALLER_DATABASE_URL", raising=False)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text(
            "TALLER_DATABASE_URL=postgresql+psycopg://u:p@h/d\n", encoding="utf-8"
        )
        monkeypatch.setenv("TALLER_ENV_FILE", str(tmp_path / ".env"))
        assert hay_configuracion_externa() is True

    def test_un_dot_env_sin_la_url_no_alcanza(
        self, carpeta: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from taller.arranque import hay_configuracion_externa

        monkeypatch.delenv("TALLER_DATABASE_URL", raising=False)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("OTRA_COSA=1\n", encoding="utf-8")
        monkeypatch.setenv("TALLER_ENV_FILE", str(tmp_path / ".env"))
        assert hay_configuracion_externa() is False


class TestCamposDesdeUrl:
    def test_separa_la_url_en_los_campos_del_formulario(self) -> None:
        from taller.arranque import campos_desde_url

        campos = campos_desde_url("postgresql+psycopg://ana:clave@servidor:5433/taller_dev")
        assert campos == {
            "host": "servidor",
            "puerto": 5433,
            "usuario": "ana",
            "contrasena": "clave",
            "base": "taller_dev",
        }

    def test_recupera_una_contrasena_con_simbolos(self) -> None:
        from taller.arranque import campos_desde_url

        url = url_desde_campos("h", 5432, "u", "a@b:c/d", "t")
        assert campos_desde_url(url)["contrasena"] == "a@b:c/d"

    def test_una_url_invalida_devuelve_vacio(self) -> None:
        from taller.arranque import campos_desde_url

        assert campos_desde_url("no es una url") == {}


class TestPermisosDelArchivo:
    def test_el_archivo_queda_solo_para_el_duenio(self, carpeta: Path) -> None:
        import os
        import stat

        guardar_configuracion(
            ConfiguracionArranque(
                database_url="postgresql+psycopg://u:p@localhost/t", nombre="X"
            )
        )
        modo = stat.S_IMODE(os.stat(ruta_configuracion()).st_mode)
        assert modo == 0o600, f"el archivo con la contraseña quedó en {oct(modo)}"
