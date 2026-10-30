"""Exportación a CSV: formato, acentos y filtros.

Lo que se prueba acá es el contrato del archivo que alguien va a abrir en Excel:
delimitador, fechas sin hora, acentos legibles y que la exportación sea lo que se
está viendo, no la tabla entera.
"""

from __future__ import annotations

import codecs
import csv
import datetime as dt
import io
from pathlib import Path

import pytest

from taller.exportacion import (
    DELIMITADOR,
    ENCABEZADOS,
    escribir_csv,
    fila_a_columnas,
    filas_a_csv,
    nombre_sugerido,
)
from taller.schemas.movimiento import MovimientoLeido


def _leer(texto: str) -> list[list[str]]:
    """Parse the CSV, discarding the empty record a trailing newline produces."""
    registros = list(csv.reader(io.StringIO(texto, newline=""), delimiter=DELIMITADOR))
    return [registro for registro in registros if registro]


def fila(**extra: object) -> MovimientoLeido:
    base: dict[str, object] = {
        "id": 1,
        "estado": "despachado",
        "fecha_entrada": dt.date(2022, 9, 21),
        "fecha_salida": dt.date(2022, 9, 26),
        "area": "Agrometeorología",
        "tipo_equipo": "CPU",
        "modelo": "Dell Vostro 230",
        "codigo_inventario": "776",
        "service_tag": "ABC123",
        "soporte": ["Juan Herrera", "Diego Davis"],
        "diagnostico": "No encendía",
        "nota": "Trajo cable",
    }
    base.update(extra)
    return MovimientoLeido.model_validate(base)


class TestFormato:
    def test_las_columnas_van_en_el_orden_documentado(self) -> None:
        columnas = fila_a_columnas(fila())
        assert len(columnas) == len(ENCABEZADOS)
        assert columnas[0] == "Despachado"
        assert columnas[3] == "Agrometeorología"
        assert columnas[6] == "776"

    def test_las_fechas_van_en_dd_mm_aaaa_sin_hora(self) -> None:
        columnas = fila_a_columnas(fila())
        assert columnas[1] == "21/09/2022"
        assert columnas[2] == "26/09/2022"
        assert ":" not in columnas[1]

    def test_los_campos_vacios_quedan_vacios_no_como_none(self) -> None:
        columnas = fila_a_columnas(fila(service_tag=None, nota=None, soporte=[]))
        assert columnas[7] == ""
        assert columnas[8] == ""
        assert columnas[10] == ""
        assert "None" not in columnas

    def test_los_soportes_se_unen_con_coma(self) -> None:
        assert fila_a_columnas(fila())[8] == "Juan Herrera, Diego Davis"

    def test_el_estado_sale_con_su_palabra(self) -> None:
        assert fila_a_columnas(fila(estado="en_taller"))[0] == "En taller"
        assert fila_a_columnas(fila(estado="sin_datos"))[0] == "Sin datos"

    def test_la_marca_de_revision_sale_como_si_o_no(self) -> None:
        assert fila_a_columnas(fila())[11] == "No"
        assert fila_a_columnas(fila(requiere_revision=True))[11] == "Sí"


class TestTexto:
    def test_el_encabezado_es_la_primera_linea(self) -> None:
        texto = filas_a_csv([fila()])
        primera = texto.split("\r\n")[0]
        assert primera.split(DELIMITADOR) == list(ENCABEZADOS)

    def test_usa_punto_y_coma_para_que_excel_lo_abra_bien(self) -> None:
        texto = filas_a_csv([fila()])
        assert ";" in texto
        assert texto.count("\r\n") == 2  # encabezado + una fila

    def test_una_nota_con_punto_y_coma_se_entrecomilla(self) -> None:
        texto = filas_a_csv([fila(nota="CPU; monitor")])
        registros = list(csv.reader(io.StringIO(texto), delimiter=DELIMITADOR))
        assert registros[1][10] == "CPU; monitor"

    def test_una_nota_con_saltos_de_linea_no_rompe_el_registro(self) -> None:
        texto = filas_a_csv([fila(nota="linea uno\nlinea dos")])
        registros = _leer(texto)
        assert len(registros) == 2, "el salto de línea partió la fila en dos"
        assert registros[1][10] == "linea uno\nlinea dos"

    def test_sin_filas_solo_queda_el_encabezado(self) -> None:
        texto = filas_a_csv([])
        assert len([linea for linea in texto.split("\r\n") if linea]) == 1


class TestArchivo:
    def test_escribe_con_bom_para_que_excel_muestre_los_acentos(
        self, tmp_path: Path
    ) -> None:
        destino = tmp_path / "salida.csv"
        cantidad = escribir_csv(destino, [fila()])

        assert cantidad == 1
        assert destino.read_bytes().startswith(codecs.BOM_UTF8)
        assert "Agrometeorología" in destino.read_text(encoding="utf-8-sig")

    def test_crea_el_directorio_si_no_existe(self, tmp_path: Path) -> None:
        destino = tmp_path / "reportes" / "mes.csv"
        escribir_csv(destino, [fila()])
        assert destino.is_file()

    def test_el_nombre_sugerido_lleva_fecha_y_hora(self) -> None:
        assert nombre_sugerido("2026-10-30 14:35") == "movimientos-20261030-1435.csv"

    def test_exportar_dos_veces_sobreescribe_sin_duplicar(self, tmp_path: Path) -> None:
        destino = tmp_path / "salida.csv"
        escribir_csv(destino, [fila()])
        escribir_csv(destino, [fila(), fila(id=2)])
        texto = destino.read_bytes().decode("utf-8-sig")
        assert len(_leer(texto)) == 3, "el segundo archivo arrastró filas del primero"


@pytest.mark.parametrize("estado", ["despachado", "en_taller", "sin_datos"])
def test_cada_estado_se_exporta_sin_error(estado: str) -> None:
    texto = filas_a_csv([fila(estado=estado)])
    assert len(_leer(texto)) == 2, "encabezado más una fila"
