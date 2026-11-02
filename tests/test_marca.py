"""La identidad de la aplicación es configuración, no código.

El repositorio se publica genérico; quien lo despliega le pone su nombre y su logo
con un ``branding.json`` que no se commitea.
"""

from __future__ import annotations

import json
from pathlib import Path

from taller.ui.marca import (
    DESCRIPCION_GENERICA,
    LOGO_GENERICO,
    NOMBRE_GENERICO,
    cargar_marca,
)


class TestSinConfiguracion:
    def test_devuelve_los_valores_genericos(self, tmp_path: Path) -> None:
        marca = cargar_marca(tmp_path / "no-existe.json")
        assert marca.nombre == NOMBRE_GENERICO
        assert marca.descripcion == DESCRIPCION_GENERICA
        assert marca.logo == LOGO_GENERICO

    def test_el_logo_generico_existe_en_el_paquete(self) -> None:
        assert LOGO_GENERICO.is_file(), "el repo debe traer su propia marca neutra"


class TestConfiguracionPropia:
    def _logo(self, tmp_path: Path) -> Path:
        logo = tmp_path / "mi-logo.png"
        logo.write_bytes(b"\x89PNG\r\n\x1a\n")
        return logo

    def test_lee_nombre_descripcion_y_logo(self, tmp_path: Path) -> None:
        logo = self._logo(tmp_path)
        config = tmp_path / "branding.json"
        config.write_text(
            json.dumps(
                {
                    "nombre": "Mi Taller",
                    "organizacion": "Mi Empresa",
                    "descripcion": "Equipos de la empresa",
                    "logo": "mi-logo.png",
                }
            ),
            encoding="utf-8",
        )

        marca = cargar_marca(config)

        assert marca.nombre == "Mi Taller"
        assert marca.organizacion == "Mi Empresa"
        assert marca.descripcion == "Equipos de la empresa"
        assert marca.logo == logo
        assert marca.titulo_ventana == "Mi Taller"

    def test_un_logo_inexistente_cae_en_el_generico(self, tmp_path: Path) -> None:
        config = tmp_path / "branding.json"
        config.write_text(json.dumps({"nombre": "X", "logo": "no-existe.png"}), encoding="utf-8")
        assert cargar_marca(config).logo == LOGO_GENERICO

    def test_un_archivo_roto_no_rompe_la_aplicacion(self, tmp_path: Path) -> None:
        config = tmp_path / "branding.json"
        config.write_text("{ esto no es json", encoding="utf-8")
        marca = cargar_marca(config)
        assert marca.nombre == NOMBRE_GENERICO

    def test_las_claves_desconocidas_se_ignoran(self, tmp_path: Path) -> None:
        config = tmp_path / "branding.json"
        config.write_text(json.dumps({"nombre": "X", "color": "rojo"}), encoding="utf-8")
        assert cargar_marca(config).nombre == "X"

    def test_un_nombre_vacio_cae_en_el_generico(self, tmp_path: Path) -> None:
        config = tmp_path / "branding.json"
        config.write_text(json.dumps({"nombre": "   "}), encoding="utf-8")
        assert cargar_marca(config).nombre == NOMBRE_GENERICO

    def test_la_variable_de_entorno_elige_el_archivo(
        self, tmp_path: Path, monkeypatch: object
    ) -> None:
        config = tmp_path / "otra.json"
        config.write_text(json.dumps({"nombre": "Desde el entorno"}), encoding="utf-8")
        monkeypatch.setenv("TALLER_BRANDING", str(config))  # type: ignore[attr-defined]
        assert cargar_marca().nombre == "Desde el entorno"
