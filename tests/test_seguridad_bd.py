"""El auditor de seguridad de la base: veredicto a partir de hechos.

La mayoría de las pruebas no tocan la base: le dan los hechos y miran el
veredicto. La última sí la toca, para dejar clavado que hoy no hay nada que
arreglar en esta instalación.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _cargar() -> object:
    spec = importlib.util.spec_from_file_location(
        "verificar_seguridad_bd", RAIZ / "scripts" / "verificar_seguridad_bd.py"
    )
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    # dataclasses busca el módulo en sys.modules al procesar la clase
    sys.modules["verificar_seguridad_bd"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


auditor = _cargar()


def _hechos(**cambios: object):
    base = {
        "rol": "taller",
        "cifrado_contrasenas": "scram-sha-256",
        "listen_addresses": "localhost",
        "ssl": "off",
        "reglas": [],
    }
    base.update(cambios)
    return auditor.Hechos(**base)  # type: ignore[attr-defined]


def _fallas(hallazgos: list) -> list[str]:
    return [h.titulo for h in hallazgos if h.nivel == auditor.FALLA]  # type: ignore[attr-defined]


class TestPrivilegios:
    def test_un_rol_superusuario_es_falla(self) -> None:
        fallas = _fallas(auditor.auditar(_hechos(rolsuper=True)))
        assert any("SUPERUSER" in titulo for titulo in fallas)

    def test_crear_roles_sigue_siendo_falla(self) -> None:
        fallas = _fallas(auditor.auditar(_hechos(rolcreaterole=True)))
        assert len(fallas) == 1

    def test_crear_bases_es_aviso_y_no_falla(self) -> None:
        """Poder crear la base es lo que permite la auto-creación del programa."""
        hallazgos = auditor.auditar(_hechos(rolcreatedb=True))
        assert _fallas(hallazgos) == []
        assert any(
            h.nivel == auditor.AVISO and "crear bases" in h.titulo for h in hallazgos
        ), [h.titulo for h in hallazgos]

    def test_un_rol_acotado_no_genera_fallas(self) -> None:
        assert _fallas(auditor.auditar(_hechos())) == []

    def test_scram_sha_256_no_genera_fallas(self) -> None:
        assert _fallas(auditor.auditar(_hechos())) == []

    def test_md5_es_falla(self) -> None:
        hallazgos = auditor.auditar(_hechos(cifrado_contrasenas="md5"))
        assert any("md5" in texto for texto in _fallas(hallazgos))
        arreglo = [h.arreglo for h in hallazgos if h.nivel == auditor.FALLA][0]  # type: ignore[attr-defined]
        assert "scram-sha-256" in arreglo


class TestReglasDeRed:
    def test_trust_desde_la_red_es_falla(self) -> None:
        reglas = [
            {
                "line_number": 130,
                "type": "host",
                "database": ["taller_dev"],
                "user_name": ["all"],
                "address": "192.168.1.0/24",
                "auth_method": "trust",
            }
        ]
        fallas = _fallas(auditor.auditar(_hechos(reglas=reglas)))
        assert len(fallas) == 1
        assert "192.168.1.0/24" in fallas[0]

    def test_trust_en_loopback_es_solo_aviso(self) -> None:
        reglas = [
            {
                "line_number": 133,
                "type": "host",
                "database": ["taller_dev"],
                "user_name": ["taller_ro"],
                "address": "127.0.0.1/32",
                "auth_method": "trust",
            }
        ]
        hallazgos = auditor.auditar(_hechos(reglas=reglas))
        assert _fallas(hallazgos) == []
        assert any(h.nivel == auditor.AVISO for h in hallazgos)  # type: ignore[attr-defined]

    def test_las_reglas_de_replicacion_no_son_ruido(self) -> None:
        reglas = [
            {
                "line_number": 121,
                "type": "local",
                "database": ["replication"],
                "user_name": ["all"],
                "address": "",
                "auth_method": "trust",
            }
        ]
        hallazgos = auditor.auditar(_hechos(reglas=reglas))
        assert not any(
            "replicación" in h.titulo or "regla 121" in h.titulo for h in hallazgos
        )

    def test_si_no_se_pueden_leer_las_reglas_lo_dice_sin_fallar(self) -> None:
        hallazgos = auditor.auditar(_hechos(reglas_legibles=False))
        assert _fallas(hallazgos) == []
        assert any(
            "No se pudieron leer las reglas" in h.titulo for h in hallazgos
        ), [h.titulo for h in hallazgos]

    def test_una_red_cerrada_se_informa(self) -> None:
        hallazgos = auditor.auditar(_hechos())
        assert any("Ninguna regla de red" in h.titulo for h in hallazgos), [
            h.titulo for h in hallazgos
        ]

    def test_escuchar_en_todas_las_interfaces_es_aviso(self) -> None:
        hallazgos = auditor.auditar(_hechos(listen_addresses="*"))
        assert _fallas(hallazgos) == []
        assert any(h.nivel == auditor.AVISO for h in hallazgos)  # type: ignore[attr-defined]


class TestSoloLectura:
    def test_si_puede_escribir_es_falla(self) -> None:
        hallazgos = auditor.auditar(
            _hechos(tablas_escribibles_por_solo_lectura=["movimiento"])
        )
        fallas = _fallas(hallazgos)
        assert len(fallas) == 1
        detalle = [h.detalle for h in hallazgos if h.nivel == auditor.FALLA][0]  # type: ignore[attr-defined]
        assert "movimiento" in detalle

    def test_si_solo_lee_no_genera_fallas(self) -> None:
        assert _fallas(auditor.auditar(_hechos())) == []


class TestContraLaBaseReal:
    def test_la_instalacion_actual_no_tiene_nada_que_arreglar(self) -> None:
        codigo = auditor.main([])  # type: ignore[attr-defined]
        assert codigo == 0, "el auditor encontró algo que hay que arreglar"
