#!/usr/bin/env python
"""Audit the database access rules and say what has to be fixed.

Corre contra la base configurada (``TALLER_DATABASE_URL`` o el asistente) y
revisa lo que de verdad protege los datos: privilegios del rol, cifrado de
contraseñas, reglas de red y quién puede escribir.

Códigos de salida: ``0`` todo bien o solo avisos, ``1`` hay algo que arreglar,
``2`` no se pudo conectar.

Uso:
    uv run python scripts/verificar_seguridad_bd.py
    uv run python scripts/verificar_seguridad_bd.py --solo-lectura taller_ro
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

from sqlalchemy import text

OK = "OK"
AVISO = "AVISO"
FALLA = "FALLA"

# Un trust solo es tolerable en loopback: significa que cualquier proceso local
# entra como ese rol sin contraseña.
LOOPBACK = ("127.0.0.1", "::1", "127.0.0.1/32", "::1/128")


def _texto(valor: object) -> str:
    """pg_hba_file_rules devuelve listas cuando la regla vale para varios."""
    if isinstance(valor, list | tuple):
        return ", ".join(str(v) for v in valor)
    return "" if valor is None else str(valor)


@dataclass
class Hallazgo:
    nivel: str
    titulo: str
    detalle: str
    arreglo: str = ""


@dataclass
class Hechos:
    """Lo que se leyó de la base, separado de las conclusiones."""

    rol: str = ""
    rolsuper: bool = False
    rolcreatedb: bool = False
    rolcreaterole: bool = False
    cifrado_contrasenas: str = ""
    reglas: list[dict[str, object]] = field(default_factory=list)
    listen_addresses: str = ""
    ssl: str = ""
    reglas_legibles: bool = True
    tablas_escribibles_por_solo_lectura: list[str] = field(default_factory=list)
    superusuarios_con_login: list[str] = field(default_factory=list)


def auditar(hechos: Hechos) -> list[Hallazgo]:
    """Conclude from the facts. Sin base de datos, para poder probarlo."""
    hallazgos: list[Hallazgo] = []

    peligrosos = [
        nombre
        for nombre, activo in (
            ("SUPERUSER", hechos.rolsuper),
            ("CREATEROLE", hechos.rolcreaterole),
        )
        if activo
    ]
    if peligrosos:
        hallazgos.append(
            Hallazgo(
                FALLA,
                f"El rol de la aplicación ({hechos.rol}) tiene {', '.join(peligrosos)}",
                "Un error de la aplicación con estos privilegios no tiene freno.",
                f"ALTER ROLE {hechos.rol} NOSUPERUSER NOCREATEROLE;",
            )
        )
    else:
        hallazgos.append(
            Hallazgo(
                OK,
                f"El rol de la aplicación ({hechos.rol}) no es superusuario",
                "Sin SUPERUSER ni CREATEROLE.",
            )
        )
        if hechos.rolcreatedb:
            hallazgos.append(
                Hallazgo(
                    AVISO,
                    f"El rol ({hechos.rol}) puede crear bases de datos",
                    "Está a propósito: permite que el programa cree la base si "
                    "falta. No es un lío, pero un rol sin CREATEDB es más seguro.",
                    "Si preferís el control estricto: ALTER ROLE ... NOCREATEDB y "
                    "crear la base una vez a mano.",
                )
            )

    if hechos.cifrado_contrasenas == "scram-sha-256":
        hallazgos.append(
            Hallazgo(OK, "Las contraseñas se guardan con scram-sha-256", "Cifrado moderno.")
        )
    else:
        hallazgos.append(
            Hallazgo(
                FALLA,
                f"password_encryption es «{hechos.cifrado_contrasenas}»",
                "md5 está roto; sin cifrado fuerte una contraseña filtrada se reutiliza.",
                "ALTER SYSTEM SET password_encryption = 'scram-sha-256'; "
                "-- y volver a fijar cada contraseña",
            )
        )

    # Reglas de red: ningún trust fuera de loopback, y ninguno para todos los roles.
    reglas_con_falla = False
    for regla in hechos.reglas:
        # Las reglas de replicación vienen así por defecto y no exponen los datos.
        if "replication" in _texto(regla.get("database")):
            continue
        metodo = _texto(regla.get("auth_method"))
        if metodo != "trust":
            continue
        tipo = _texto(regla.get("type"))
        direccion = _texto(regla.get("address"))
        usuario = _texto(regla.get("user_name")) or "?"
        base = _texto(regla.get("database")) or "?"
        linea = regla.get("line_number")
        remota = tipo == "host" and direccion not in LOOPBACK
        todos_los_roles = usuario in ("{all}", "all")
        if remota:
            reglas_con_falla = True
            hallazgos.append(
                Hallazgo(
                    FALLA,
                    f"La regla {linea} acepta conexiones sin contraseña desde {direccion}",
                    f"base {base}, usuario {usuario}. Cualquiera en la red entra.",
                    "Cambiar trust por scram-sha-256 en esa línea de pg_hba.conf.",
                )
            )
        elif todos_los_roles or tipo == "local":
            hallazgos.append(
                Hallazgo(
                    AVISO,
                    f"La regla {linea} confía en quien se conecte ({tipo} {direccion or 'socket'})",
                    f"base {base}, usuario {usuario}. En loopback alcanza a cualquier "
                    "usuario del sistema operativo.",
                    "Usar peer o scram-sha-256 si no hace falta esta comodidad.",
                )
            )

    if not hechos.reglas_legibles:
        hallazgos.append(
            Hallazgo(
                AVISO,
                "No se pudieron leer las reglas de red",
                "pg_hba_file_rules exige superusuario; el rol de la aplicación no lo es "
                "(y está bien que no lo sea).",
                "Repetir este chequeo con un rol administrador: --admin-url",
            )
        )
    elif not reglas_con_falla:
        hallazgos.append(
            Hallazgo(OK, "Ninguna regla de red confía en conexiones remotas", "Revisado pg_hba.")
        )

    escucha = hechos.listen_addresses or ""
    if escucha in ("*", "0.0.0.0", "::"):
        hallazgos.append(
            Hallazgo(
                AVISO,
                f"PostgreSQL escucha en todas las interfaces ({escucha})",
                "Solo vale si el firewall cierra el 5432 hacia afuera.",
                "listen_addresses = '192.168.x.x' en postgresql.conf",
            )
        )
    else:
        hallazgos.append(
            Hallazgo(OK, f"Escucha solo en «{escucha}»", "No expuesto más allá de eso.")
        )

    if (hechos.ssl or "").lower() in ("on", "1", "true"):
        hallazgos.append(Hallazgo(OK, "TLS habilitado en el servidor", "ssl = on"))
    else:
        hallazgos.append(
            Hallazgo(
                AVISO,
                "TLS deshabilitado en el servidor",
                "En una red local conmutada puede ser aceptable; fuera de ella, no.",
                "ssl = on y exigir sslmode=require en la cadena de conexión",
            )
        )

    if hechos.tablas_escribibles_por_solo_lectura:
        hallazgos.append(
            Hallazgo(
                FALLA,
                f"El rol de solo lectura puede escribir en "
                f"{len(hechos.tablas_escribibles_por_solo_lectura)} tabla(s)",
                ", ".join(hechos.tablas_escribibles_por_solo_lectura[:5]),
                "REVOKE INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public FROM ese rol;",
            )
        )
    else:
        hallazgos.append(
            Hallazgo(OK, "El rol de solo lectura no puede escribir", "Solo SELECT.")
        )

    if hechos.superusuarios_con_login:
        hallazgos.append(
            Hallazgo(
                AVISO,
                "Roles superusuario que pueden conectarse: "
                + ", ".join(hechos.superusuarios_con_login),
                "Necesario para administrar, pero estas cuentas no deben usarse "
                "desde la aplicación.",
                "Que la cadena de conexión de la aplicación use un rol acotado.",
            )
        )

    return hallazgos


def _reglas_de_red(conexion) -> list[dict[str, object]] | None:  # noqa: ANN001
    """Las reglas de pg_hba, o ``None`` si este rol no puede verlas."""
    try:
        # Savepoint: al rol de la aplicación le niegan la vista y, sin esto, el
        # error deja la transacción entera abortada y no se puede seguir leyendo.
        with conexion.begin_nested():
            return [
                dict(fila._mapping)
                for fila in conexion.execute(
                    text(
                        "select line_number, type, database, user_name, address, "
                        "auth_method from pg_hba_file_rules order by line_number"
                    )
                )
            ]
    except Exception:  # noqa: BLE001 - sin privilegios alcanza para seguir
        return None


def recolectar(  # noqa: ANN001
    conexion, solo_lectura: str | None, admin_url: str | None = None
) -> Hechos:
    hechos = Hechos()

    fila = conexion.execute(
        text(
            "select current_user as rol, rolsuper, rolcreatedb, rolcreaterole "
            "from pg_roles where rolname = current_user"
        )
    ).one()
    hechos.rol = fila.rol
    hechos.rolsuper = bool(fila.rolsuper)
    hechos.rolcreatedb = bool(fila.rolcreatedb)
    hechos.rolcreaterole = bool(fila.rolcreaterole)

    hechos.cifrado_contrasenas = conexion.execute(
        text("show password_encryption")
    ).scalar_one()
    hechos.listen_addresses = conexion.execute(
        text("show listen_addresses")
    ).scalar_one()
    hechos.ssl = str(conexion.execute(text("show ssl")).scalar_one())

    reglas = _reglas_de_red(conexion)
    if reglas is None and admin_url:
        from sqlalchemy import create_engine

        with create_engine(admin_url).connect() as administracion:
            reglas = _reglas_de_red(administracion)
    if reglas is None:
        hechos.reglas_legibles = False
    else:
        hechos.reglas = reglas

    hechos.superusuarios_con_login = [
        str(fila[0])
        for fila in conexion.execute(
            text("select rolname from pg_roles where rolsuper and rolcanlogin order by 1")
        )
    ]

    if solo_lectura:
        existe = conexion.execute(
            text("select 1 from pg_roles where rolname = :rol"), {"rol": solo_lectura}
        ).first()
        if existe:
            tablas = conexion.execute(
                text(
                    "select c.relname from pg_class c join pg_namespace n "
                    "on n.oid = c.relnamespace where n.nspname = 'public' "
                    "and c.relkind in ('r','v') and ("
                    "  has_table_privilege(:rol, c.oid, 'INSERT') or "
                    "  has_table_privilege(:rol, c.oid, 'UPDATE') or "
                    "  has_table_privilege(:rol, c.oid, 'DELETE')) order by 1"
                ),
                {"rol": solo_lectura},
            )
            hechos.tablas_escribibles_por_solo_lectura = [str(f[0]) for f in tablas]

    return hechos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--solo-lectura",
        default="taller_ro",
        help="rol que debería poder leer y nada más (por defecto taller_ro)",
    )
    parser.add_argument(
        "--admin-url",
        default=None,
        help="conexión de un rol administrador, para leer las reglas de red",
    )
    opciones = parser.parse_args(argv)

    from taller.database.connection import get_engine

    try:
        motor = get_engine()
        with motor.connect() as conexion:
            hechos = recolectar(conexion, opciones.solo_lectura, opciones.admin_url)
    except Exception as error:  # noqa: BLE001 - se informa y se sale con 2
        print(f"No se pudo conectar a la base: {error}", file=sys.stderr)
        return 2

    hallazgos = auditar(hechos)
    ancho = max(len(h.titulo) for h in hallazgos)
    for hallazgo in hallazgos:
        marca = {OK: "[ OK  ]", AVISO: "[AVISO]", FALLA: "[FALLA]"}[hallazgo.nivel]
        print(f"{marca} {hallazgo.titulo:<{ancho}}  {hallazgo.detalle}")
        if hallazgo.arreglo:
            print(f"        → {hallazgo.arreglo}")

    fallas = sum(1 for h in hallazgos if h.nivel == FALLA)
    avisos = sum(1 for h in hallazgos if h.nivel == AVISO)
    print()
    if fallas:
        print(f"{fallas} problema(s) que hay que arreglar, {avisos} aviso(s).")
        return 1
    print(f"Sin problemas que arreglar. {avisos} aviso(s) para revisar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
