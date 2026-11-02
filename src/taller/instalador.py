"""Instalar y desinstalar el programa, sin consola y sin rutas a mano.

Todo lo que hace el instalador vive acá, separado de la ventana: se puede probar sin
abrir una ventana ni tocar la carpeta del usuario. La ventana
(``ui/views/instalador_view.py``) solo muestra lo que estas funciones responden y
llama a las que hacen.

Reglas que respeta:

* **Nada de privilegios.** Instala donde la persona puede escribir, sin pedir
  contraseña de administrador. Si quiere instalar para todo el sistema, se le dice qué
  comando correr.
* **Nunca borra datos.** Desinstalar quita el programa y, si se pide, la
  configuración. La base de datos no se toca nunca.
* **No deja a medias.** Copia a una carpeta nueva y recién al final reemplaza: si la
  copia falla, lo que había sigue funcionando.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

NOMBRE_CARPETA = "Taller de equipos"
NOMBRE_BINARIO = "taller-equipos.exe" if os.name == "nt" else "taller-equipos"


def es_windows() -> bool:
    return os.name == "nt"


def raiz_del_programa() -> Path:
    """La carpeta donde está el programa que se está ejecutando."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def carpeta_configuracion() -> Path:
    """La misma carpeta que usa la aplicación para guardar su configuración."""
    from taller.arranque import carpeta_configuracion as la_de_arranque

    return la_de_arranque()


def destino_usuario() -> Path:
    """Dónde instala sin permisos de administrador."""
    if es_windows():
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "Programs" / NOMBRE_CARPETA
    return Path.home() / ".local" / "lib" / "taller-equipos"


def destino_sistema() -> Path:
    """Dónde instala para todos. En Linux pide permisos de administrador."""
    if es_windows():
        base = Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
        return base / NOMBRE_CARPETA
    return Path("/usr/local/lib/taller-equipos")


def candidatos() -> list[Path]:
    """Todas las carpetas donde puede haber una instalación."""
    vistos: list[Path] = []
    for candidato in (destino_usuario(), destino_sistema()):
        if candidato not in vistos:
            vistos.append(candidato)
    return vistos


@dataclass
class Instalacion:
    """Una copia del programa que hay en el disco."""

    ruta: Path
    version: str = ""
    es_la_que_corre: bool = False

    @property
    def tamano_mb(self) -> float:
        total = 0
        for archivo in self.ruta.rglob("*"):
            try:
                total += archivo.stat().st_size
            except OSError:
                continue
        return round(total / (1024 * 1024), 1)


def _version_en(carpeta: Path) -> str:
    """Lee la versión del ejecutable de esa carpeta, sin ejecutarlo si se puede."""
    import json

    for candidato in (carpeta / "_internal" / "version.json", carpeta / "version.json"):
        if candidato.is_file():
            try:
                return str(json.loads(candidato.read_text(encoding="utf-8"))["version"])
            except (OSError, ValueError, KeyError):
                continue
    return ""


def detectar() -> list[Instalacion]:
    """Las instalaciones que existen de verdad, no las que podrían existir."""
    actual = raiz_del_programa().resolve()
    encontradas: list[Instalacion] = []
    for candidato in candidatos():
        if not (candidato / NOMBRE_BINARIO).is_file():
            continue
        encontradas.append(
            Instalacion(
                ruta=candidato,
                version=_version_en(candidato),
                es_la_que_corre=candidato.resolve() == actual,
            )
        )
    return encontradas


@dataclass
class Resultado:
    """Qué pasó, en palabras que se pueden mostrar."""

    ok: bool
    mensaje: str
    detalles: list[str] = field(default_factory=list)


def _copiar(origen: Path, destino: Path) -> None:
    """Copia el árbol a ``destino`` sin dejar nunca una instalación a medias."""
    nueva = destino.with_name(destino.name + ".nueva")
    if nueva.exists():
        shutil.rmtree(nueva)
    shutil.copytree(origen, nueva)
    if destino.exists():
        shutil.rmtree(destino)
    nueva.rename(destino)


def _crear_lanzador(destino: Path) -> Path:
    """Un solo archivo que abre el programa, sin depender del PATH."""
    if es_windows():
        lanzador = destino / f"{NOMBRE_CARPETA}.cmd"
        lanzador.write_text(
            f'@echo off\r\nstart "" "{destino / NOMBRE_BINARIO}"\r\n', encoding="utf-8"
        )
        return lanzador
    en_bin = Path.home() / ".local" / "bin" / "taller-equipos"
    en_bin.parent.mkdir(parents=True, exist_ok=True)
    en_bin.write_text(
        "#!/usr/bin/env bash\nexec " + f'"{destino / NOMBRE_BINARIO}" "$@"\n',
        encoding="utf-8",
    )
    en_bin.chmod(0o755)
    return en_bin


def _crear_acceso_escritorio(destino: Path) -> Path | None:
    """La entrada para el menú de aplicaciones (Linux) o el escritorio (Windows)."""
    if es_windows():
        escritorio = Path.home() / "Desktop"
        if not escritorio.is_dir():
            return None
        acceso = escritorio / f"{NOMBRE_CARPETA}.cmd"
        acceso.write_text(
            f'@echo off\r\nstart "" "{destino / NOMBRE_BINARIO}"\r\n', encoding="utf-8"
        )
        return acceso

    entrada = (
        Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        / "applications"
        / "taller-equipos.desktop"
    )
    entrada.parent.mkdir(parents=True, exist_ok=True)
    icono = destino / "_internal" / "taller" / "ui" / "assets" / "logo.png"
    entrada.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={NOMBRE_CARPETA}\n"
        "Comment=Registro de entrada y salida de equipos\n"
        f'Exec="{destino / NOMBRE_BINARIO}"\n'
        f"Icon={icono}\n"
        "Terminal=false\n"
        "Categories=Office;Database;\n",
        encoding="utf-8",
    )
    entrada.chmod(0o755)
    return entrada


def _restos_de(prefijo: Path) -> list[Path]:
    """Lanzador y entrada del menú que deja una instalación en ese prefijo."""
    if es_windows():
        return []
    return [
        prefijo / "bin" / "taller-equipos",
        prefijo / "share" / "applications" / "taller-equipos.desktop",
        prefijo / "share" / "icons" / "hicolor" / "256x256" / "apps" / "taller-equipos.png",
        prefijo / "share" / "taller-equipos",
    ]


def instalar(destino: Path | None = None) -> Resultado:
    """Copia el programa que está corriendo a su lugar definitivo."""
    origen = raiz_del_programa()
    destino = (destino or destino_usuario()).expanduser()
    detalles: list[str] = []

    if not (origen / NOMBRE_BINARIO).is_file():
        return Resultado(False, f"No encuentro el programa en {origen}.")

    if destino.resolve() == origen.resolve():
        return Resultado(False, "Ese es el lugar donde ya está corriendo.")

    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        _copiar(origen, destino)
    except PermissionError:
        return Resultado(
            False,
            f"No tengo permiso para escribir en {destino.parent}.",
            ["Instalá para tu usuario, o pedile a un administrador que lo haga."],
        )
    except OSError as error:
        return Resultado(False, f"No se pudo copiar: {error}")
    detalles.append(f"Programa copiado a {destino}")

    for creador, descripcion in (
        (_crear_lanzador, "Lanzador"),
        (_crear_acceso_escritorio, "Acceso en el menú"),
    ):
        try:
            creado = creador(destino)
            if creado is not None:
                detalles.append(f"{descripcion}: {creado}")
        except OSError as error:
            detalles.append(f"{descripcion}: no se pudo crear ({error})")

    # El desinstalador queda junto al programa: así se lo encuentra siempre, aunque
    # el proyecto original ya no esté.
    try:
        from taller import __version__

        (destino / "version.json").write_text(
            f'{{"version": "{__version__}"}}', encoding="utf-8"
        )
    except OSError:
        pass

    return Resultado(True, "Instalado.", detalles)


def desinstalar(borrar_configuracion: bool = False) -> Resultado:
    """Quita las instalaciones que encuentre, y opcionalmente la configuración."""
    encontradas = detectar()
    detalles: list[str] = []

    if not encontradas:
        return Resultado(False, "No hay ninguna instalación para quitar.")

    sin_permiso: list[str] = []
    for instalacion in encontradas:
        try:
            shutil.rmtree(instalacion.ruta)
            detalles.append(f"Programa eliminado de {instalacion.ruta}")
        except OSError as error:
            return Resultado(False, f"No se pudo borrar {instalacion.ruta}: {error}")

        # El lanzador y la entrada del menú viven en el prefijo de la instalación:
        # en una instalación de sistema son de root y hay que decirlo, no fallar.
        prefijo = instalacion.ruta.parent.parent
        for resto in _restos_de(prefijo):
            if not resto.exists():
                continue
            try:
                resto.unlink()
                detalles.append(f"Eliminado {resto}")
            except OSError:
                sin_permiso.append(str(resto))

    if not es_windows():
        for resto in _restos_de(Path.home() / ".local"):
            if not resto.exists():
                continue
            try:
                resto.unlink()
                detalles.append(f"Eliminado {resto}")
            except OSError:
                sin_permiso.append(str(resto))

    if sin_permiso:
        detalles.append(
            "Quedaron archivos que necesitan permisos de administrador: "
            + ", ".join(sin_permiso)
            + ". Borralos con: sudo rm " + " ".join(sin_permiso)
        )

    if borrar_configuracion:
        carpeta = carpeta_configuracion()
        if carpeta.is_dir():
            try:
                shutil.rmtree(carpeta)
                detalles.append(f"Configuración eliminada: {carpeta}")
            except OSError as error:
                detalles.append(f"Configuración: no se pudo borrar ({error})")
    else:
        detalles.append(
            f"La configuración sigue en {carpeta_configuracion()} "
            "(nombre, logo, conexión y el ajuste del ingreso)."
        )

    detalles.append("La base de datos no se tocó: los datos no son del programa.")
    return Resultado(True, "Desinstalado.", detalles)
