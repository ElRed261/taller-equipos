"""Reglas de formato del código de inventario.

La institución confirmó que los códigos que parecen empezar con la letra ``O``
empiezan con un cero. Eso convierte lo que antes era una suposición en una regla,
y estas pruebas la fijan.
"""

from __future__ import annotations

import pytest

from taller.inventario import es_codigo_numerico, normalizar_codigo


class TestLetraOPorCero:
    def test_una_o_inicial_es_un_cero(self) -> None:
        assert normalizar_codigo("O2071") == "02071"

    def test_dos_o_iniciales_son_dos_ceros(self) -> None:
        assert normalizar_codigo("OO738") == "00738"

    def test_se_aplica_a_todos_los_codigos_de_la_serie(self) -> None:
        # La serie completa que traía el archivo legado.
        serie = ["O1014", "O1439", "O1497", "O1705", "O1905", "O1910", "O1912",
                 "O2016", "O2070", "O2071", "O2072", "O2118", "O2119", "O2120",
                 "O2121", "O2122", "O2127", "O2130", "O2133", "O2134", "O2135"]
        for codigo in serie:
            resultado = normalizar_codigo(codigo)
            assert resultado == "0" + codigo[1:], codigo
            assert resultado is not None and resultado.isdigit()

    def test_la_o_en_medio_no_se_toca_porque_no_se_puede_adivinar(self) -> None:
        # No aparece en los datos; si apareciera, el formateador no inventa.
        assert normalizar_codigo("1O14") == "1O14"


class TestAnchoDeCinco:
    """La serie completa es de cinco caracteres: eso lo dicen los propios datos."""

    def test_un_codigo_de_cuatro_digitos_se_completa(self) -> None:
        assert normalizar_codigo("1716") == "01716"
        assert normalizar_codigo("2071") == "02071"

    def test_un_codigo_de_tres_digitos_se_completa(self) -> None:
        assert normalizar_codigo("776") == "00776"
        assert normalizar_codigo("411") == "00411"

    def test_un_cero_inicial_escrito_por_el_usuario_se_conserva(self) -> None:
        assert normalizar_codigo("0776") == "00776"
        assert normalizar_codigo("00738") == "00738"

    def test_un_codigo_de_cinco_digitos_no_se_toca(self) -> None:
        assert normalizar_codigo("22182") == "22182"
        assert normalizar_codigo("17018") == "17018"

    def test_un_codigo_mas_largo_no_se_recorta(self) -> None:
        assert normalizar_codigo("123456") == "123456"

    def test_el_cero_solo_es_un_marcador_vacio(self) -> None:
        # La fila traía "0" como código: no es un número, es un hueco.
        assert normalizar_codigo("0") == "00000"


class TestBasuraAlrededor:
    def test_almohadilla_al_inicio(self) -> None:
        assert normalizar_codigo("#02322") == "02322"

    def test_barra_vertical_al_final(self) -> None:
        assert normalizar_codigo("01916|") == "01916"

    def test_espacio_adentro_de_un_codigo_numerico(self) -> None:
        assert normalizar_codigo("0 1710") == "01710"

    def test_espacios_alrededor(self) -> None:
        assert normalizar_codigo("  776  ") == "00776"


class TestLoQueNoEsCodigo:
    @pytest.mark.parametrize("marcador", ["N/A", "n/a", "---", "--", "NO", "NO  TIENE", "  "])
    def test_los_marcadores_de_sin_codigo_quedan_en_none(self, marcador: str) -> None:
        assert normalizar_codigo(marcador) is None

    def test_un_texto_cualquiera_no_se_toca(self) -> None:
        assert normalizar_codigo("Acer y Opiplet 7010") == "Acer y Opiplet 7010"
        assert normalizar_codigo("sondeo") == "sondeo"

    def test_un_codigo_alfanumerico_legitimo_no_se_toca(self) -> None:
        assert normalizar_codigo("YLTH614904") == "YLTH614904"


class TestEsCodigoNumerico:
    def test_solo_digitos(self) -> None:
        assert es_codigo_numerico("02071")
        assert not es_codigo_numerico("O2071")
        assert not es_codigo_numerico(None)
