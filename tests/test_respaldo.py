"""El respaldo tiene que servir antes de necesitarlo.

Estas pruebas ejecutan `scripts/respaldar.sh` de verdad contra la base de
desarrollo. Lo que fijan es lo que duele el día del incidente: que el archivo se
pueda restaurar, que no quede un respaldo a medias con nombre de bueno, y que la
retención borre lo viejo.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "respaldar.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("pg_dump") is None or not SCRIPT.is_file(),
    reason="sin pg_dump o sin el script no hay nada que probar",
)


def _correr(destino: Path, **entorno: str) -> subprocess.CompletedProcess[str]:
    limpiar_clave = entorno.pop("TALLER_RESPALDO_CLAVE", None)
    limpiar_recipiente = entorno.pop("TALLER_RESPALDO_GPG_RECIPIENTE", None)
    ambiente = {
        **os.environ,
        "TALLER_RESPALDOS": str(destino),
        "TALLER_RETENCION_DIAS": entorno.pop("retencion", "30"),
    }
    # "Sin cifrado" tiene que poder pedirse aunque el entorno tenga la variable.
    ambiente["TALLER_RESPALDO_CLAVE"] = limpiar_clave or ""
    ambiente["TALLER_RESPALDO_GPG_RECIPIENTE"] = limpiar_recipiente or ""
    ambiente.update(entorno)
    return subprocess.run(  # noqa: S603
        [str(SCRIPT)],
        capture_output=True,
        text=True,
        env=ambiente,
        cwd=RAIZ,
        timeout=120,
        check=False,
    )


def test_un_respaldo_sirve_para_restaurar(tmp_path: Path) -> None:
    resultado = _correr(tmp_path)

    assert resultado.returncode == 0, resultado.stderr
    volcados = list(tmp_path.glob("*.dump"))
    assert len(volcados) == 1

    # Lo que de verdad decide: que pg_restore pueda leerlo.
    listado = subprocess.run(  # noqa: S603
        ["pg_restore", "--list", str(volcados[0])],
        capture_output=True,
        text=True,
        check=False,
    )
    assert listado.returncode == 0, listado.stderr
    assert "TABLE DATA" in listado.stdout
    assert "movimiento" in listado.stdout


def test_deja_el_registro_y_los_conteos_del_momento(tmp_path: Path) -> None:
    assert _correr(tmp_path).returncode == 0

    registro = (tmp_path / "registro.log").read_text(encoding="utf-8")
    assert "OK" in registro
    assert "movimiento=" in registro

    resumen = next(tmp_path.glob("*.txt")).read_text(encoding="utf-8")
    # El .txt es contra qué se compara una restauración.
    assert "movimiento=" in resumen
    assert "area=" in resumen


def test_dos_corridas_no_se_pisan(tmp_path: Path) -> None:
    assert _correr(tmp_path).returncode == 0
    assert _correr(tmp_path).returncode == 0
    assert len(list(tmp_path.glob("*.dump"))) == 2


def test_un_volcado_que_falla_no_deja_un_respaldo_enganoso(tmp_path: Path) -> None:
    resultado = _correr(
        tmp_path,
        TALLER_DATABASE_URL="postgresql+psycopg://nadie:nada@127.0.0.1:5432/no_existe",
    )

    assert resultado.returncode != 0
    # Ni archivo a medias, ni con nombre definitivo.
    assert list(tmp_path.glob("*.dump")) == []


def test_la_retencion_borra_solo_lo_que_pasa_del_limite(tmp_path: Path) -> None:
    viejo = tmp_path / "taller-20200101-000000.dump"
    viejo.write_bytes(b"viejo")
    os.utime(viejo, (0, 0))  # epoch: bien viejo

    assert _correr(tmp_path, retencion="30").returncode == 0

    assert not viejo.exists(), "no borró el respaldo de hace años"
    assert len(list(tmp_path.glob("*.dump"))) == 1, "borró el respaldo de hoy"


@pytest.fixture()
def clave(tmp_path: Path) -> Path:
    """Archivo con la frase simétrica, con los permisos que exige el script."""
    archivo = tmp_path / "clave"
    archivo.write_text("una-frase-larga-y-unica\n", encoding="utf-8")
    archivo.chmod(0o600)
    return archivo


class TestCifrado:
    """El volcado tiene nombres de personas: sale del servidor cifrado o no sale."""

    def test_con_clave_el_archivo_queda_cifrado(
        self, tmp_path: Path, clave: Path
    ) -> None:
        destino = tmp_path / "respaldos"
        resultado = _correr(destino, TALLER_RESPALDO_CLAVE=str(clave))

        assert resultado.returncode == 0, resultado.stderr
        cifrados = list((destino).glob("*.dump.gpg"))
        assert len(cifrados) == 1, "no dejó un archivo cifrado"
        # Ni un volcado en claro al lado.
        assert list(destino.glob("*.dump")) == []

        cabecera = cifrados[0].read_bytes()[:2]
        assert cabecera == b"\x8c\x0d", "el archivo no parece cifrado con gpg"

        # Sin la clave no se puede restaurar.
        sin_clave = subprocess.run(  # noqa: S603
            ["pg_restore", "--list", str(cifrados[0])],
            capture_output=True,
            text=True,
            check=False,
        )
        assert sin_clave.returncode != 0

    def test_la_clave_con_permisos_abiertos_se_rechaza(
        self, tmp_path: Path, clave: Path
    ) -> None:
        abierta = tmp_path / "clave-abierta"
        abierta.write_text(clave.read_text(encoding="utf-8"), encoding="utf-8")
        abierta.chmod(0o644)

        destino = tmp_path / "respaldos"
        resultado = _correr(destino, TALLER_RESPALDO_CLAVE=str(abierta))

        assert resultado.returncode != 0
        assert "permisos" in resultado.stdout.lower()
        assert list(destino.glob("*.dump*")) == []

    def test_avisa_cuando_no_se_cifra(self, tmp_path: Path) -> None:
        destino = tmp_path / "respaldos"
        resultado = _correr(
            destino, TALLER_RESPALDO_CLAVE="", TALLER_RESPALDO_GPG_RECIPIENTE=""
        )

        assert resultado.returncode == 0
        assert "NO se cifra" in resultado.stdout

    def test_el_registro_dice_si_esta_cifrado(
        self, tmp_path: Path, clave: Path
    ) -> None:
        destino = tmp_path / "respaldos"
        assert (
            _correr(destino, TALLER_RESPALDO_CLAVE=str(clave)).returncode == 0
        )
        registro = (destino / "registro.log").read_text(encoding="utf-8")
        assert "cifrado=simetrico" in registro


def _archive_mode_encendido() -> bool:
    resultado = subprocess.run(  # noqa: S603
        ["psql", "-X", "-q", "-A", "-t", "-d", "postgres", "-c", "show archive_mode"],
        capture_output=True,
        text=True,
        check=False,
    )
    return resultado.stdout.strip() == "on"


@pytest.mark.skipif(
    not _archive_mode_encendido(),
    reason="sin archive_mode no se puede aspirar a PITR",
)
class TestRespaldoBase:
    """El respaldo base es el punto de partida del PITR: tiene que verificarse."""

    def test_deja_un_base_verificado_y_cifrado(
        self, tmp_path: Path, clave: Path
    ) -> None:
        destino = tmp_path / "respaldos"
        resultado = subprocess.run(  # noqa: S603
            [str(RAIZ / "scripts" / "respaldar_base.sh")],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "TALLER_RESPALDOS": str(destino),
                "TALLER_RESPALDO_CLAVE": str(clave),
            },
            cwd=RAIZ,
            timeout=300,
            check=False,
        )

        assert resultado.returncode == 0, resultado.stdout + resultado.stderr
        assert "verificado con pg_verifybackup" in resultado.stdout
        bases = list(destino.glob("base-*.tar.gz.gpg"))
        assert len(bases) == 1
        assert "OK base" in (destino / "registro.log").read_text(encoding="utf-8")

    def test_sin_clave_avisa_que_viaja_entera_sin_cifrar(self, tmp_path: Path) -> None:
        destino = tmp_path / "respaldos"
        resultado = subprocess.run(  # noqa: S603
            [str(RAIZ / "scripts" / "respaldar_base.sh")],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "TALLER_RESPALDOS": str(destino),
                "TALLER_RESPALDO_CLAVE": "",
                "TALLER_RESPALDO_GPG_RECIPIENTE": "",
            },
            cwd=RAIZ,
            timeout=300,
            check=False,
        )

        assert resultado.returncode == 0
        assert "NO se cifra" in resultado.stdout
        assert len(list(destino.glob("base-*.tar.gz"))) == 1
