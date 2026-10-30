---
name: taller-equipos
description: Non-negotiable rules for the taller-equipos project (PySide6 desktop app over PostgreSQL). Use for any work on its database schema, ETL, repositories or Qt models, and before adding a column, an index or a QTableWidget.
---

# taller-equipos: project rules

This project replaces a legacy .NET WinForms `DataGridView` export with a
normalized PostgreSQL schema and a PySide6 client. The architecture notes are in
`docs/arquitectura.md`; read them before changing behaviour. The rules
below exist because each one was already paid for once.

## Data rules

1. **The green/red indicator is derived, never stored.** Query
   `v_movimiento_estado` (values `en_taller`, `despachado`, `sin_datos`). Never
   add an `estado` or `despachado` boolean column: it desynchronises the moment
   someone edits `fecha_salida`.
2. **Business dates are `DATE`.** `fecha_entrada` and `fecha_salida` carry no
   time. Every timestamp in the legacy source is `12:00:00 a. m.`, so a
   `TIMESTAMPTZ` would imply precision that does not exist. `creado_en`,
   `actualizado_en` and `revisado_en` stay `TIMESTAMPTZ`.
3. **`requiere_revision` is import-only.** `ck_movimiento_revision_solo_legado`
   forbids it on `origen = 'app'`. It is the single key that opens
   `ck_movimiento_fechas`. Do not relax either constraint to "fix" an insert
   error; fix the data or flag the row.
4. **Do not rewrite `codigo_inventario`.** Values like `O2071` or `OO738` keep
   their letter O. Whether it is a zero cannot be decided from the data; they
   are reported, not guessed. Explicit no-code markers (`N/A`, `---`, `NO
   TIENE`) are already NULL.
5. **There is no `equipo` entity.** Inventory codes repeat legitimately (the
   same machine comes back). `movimiento` is the ticket; `codigo_inventario` is
   an attribute.
6. **Nothing is deleted physically.** Catalogs use `activo = false`. Foreign
   keys are `ON DELETE RESTRICT`.

## Code rules

7. **SQLAlchemy 2.0 typed syntax only.** `Mapped[...]`, `mapped_column`,
   `select()`. No legacy `session.query()`.
8. **One `Session` per unit of work**, obtained from
   `taller.database.connection.session_scope()`. Never store a `Session` on a
   widget, never share one across threads or Qt signals.
9. **No `QTableWidget`.** Tables go through `QAbstractTableModel` plus
   `QSortFilterProxyModel`, so filtering and editing stay testable.
10. **Validate before writing.** Every edit runs through the Pydantic schema;
    on failure the cell reverts and no `dataChanged` is emitted.
11. **Measure before indexing.** The search path is the in-memory proxy over
    normalized text. Do not add a `pg_trgm` index or a server-side search query
    until there is a measurement showing the proxy is not enough. If you ever
    do, `unaccent()` is not `IMMUTABLE`: it needs a wrapper function.

## Environment

12. **Postgres is a keg-only Homebrew install**, not a system service:

    ```bash
    PGBIN=/home/linuxbrew/.linuxbrew/opt/postgresql@18/bin
    DATA=/home/linuxbrew/.linuxbrew/var/postgresql@18
    $PGBIN/pg_ctl -D "$DATA" -l "$DATA/server.log" -o "-c listen_addresses=localhost -p 5432" start
    ```

13. **Two roles.** `taller` owns the schema and needs a password even on
    loopback; `taller_ro` is loopback-only, passwordless and `SELECT`-only. The
    MCP server and any agent tooling use `taller_ro`. Never give an agent the
    application role.
14. **Run tests with `./.venv/bin/python -m pytest`**, not `pytest`: the
    `pytest` on `PATH` is wrapped by this environment and swallows the report
    ("No tests collected" even when tests ran).

## Migration

15. The ETL is idempotent by SHA-256 (`importacion`) and by
    `UNIQUE (origen, legacy_linea)`. Re-running it must never duplicate rows.
    A new dirty value is resolved through `mapeo_legacy`, not by patching the
    loop.
