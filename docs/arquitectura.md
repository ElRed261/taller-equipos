# Architecture

A desktop application that records the intake and dispatch of IT equipment in a
workshop, replacing a legacy `.NET WinForms` export (a semicolon-delimited text
file produced by dumping a `DataGridView`). Several technicians use it at the
same time over the local network.

## Layers

```text
src/taller/
  main.py            entry point: user, connection guard, window
  servicios.py       the only seam between widgets and the database
  inventario.py      inventory-code rules (one definition, three callers)
  formato.py         dd/mm/aaaa, never a time
  exportacion.py     CSV writer, pure functions
  database/
    models.py        SQLAlchemy 2.0 typed models
    repositories.py  every query; never commits; returns DTOs
    connection.py    engine and session_scope
  schemas/           Pydantic: the validation boundary
  etl/               one-shot import of the legacy export
  ui/                theme, icons, models, delegates, views
```

Three rules hold the layering together:

- **Repositories never commit.** The caller owns the transaction through
  `session_scope()`, which is what lets the integration tests run against a real
  database and roll everything back.
- **Repositories and services return DTOs, never ORM instances.** A detached ORM
  object crossing a Qt thread boundary is a `DetachedInstanceError` waiting for
  the first lazy access.
- **One `Session` per operation.** A widget never sees one.

## The database

Catalogs (`tipo_equipo`, `area`, `tecnico`) hold the only allowed values, with
logical delete (`activo`). `movimiento` is the ticket. `movimiento_tecnico` links
several technicians to one ticket.

Three decisions are load-bearing:

1. **The green/red indicator is derived, never stored.** The view
   `v_movimiento_estado` computes `estado` from `fecha_salida`, so it cannot
   desynchronise when someone edits a row.
2. **Business dates are `DATE`.** Every timestamp in the legacy export was
   midnight, so a `TIMESTAMPTZ` would promise a precision the data does not have.
3. **`requiere_revision` is the only escape hatch** from the date-order CHECK, and
   only imported rows may carry it (`ck_movimiento_revision_solo_legado`).

## The legacy import

The export has 568 rows with empty fields where the source had nothing,
free-text departments written many ways, and dates typed in the wrong field. The
ETL corrects only what has **one deterministic correction** and flags the rest:

- an implausible year (`1023`) moves one century;
- a departure earlier than the intake whose year alone explains the gap is a typo;
- a missing intake is inferred only when its neighbours bound it within a week;
- everything else is imported as-is with `requiere_revision`, never guessed.

The run is idempotent twice over: the file SHA-256 is recorded, and
`UNIQUE (origen, legacy_linea)` prevents duplicates.

## Inventory codes

The series is five characters wide. A leading `O` in an otherwise numeric code
means a zero (`O2071` → `02071`), junk around a numeric core is removed
(`#02322`, `01916|`), leading zeros are kept, and nothing is padded beyond the
canonical width. Values that are not codes (model names typed into the column) are
left alone. The rule lives in `inventario.py` and is used by the form, the schema
and the ETL.

## Testing

```bash
./.venv/bin/python -m pytest        # the `pytest` on PATH is wrapped and eats the report
```

The suites split by what they need:

- `test_legacy_csv.py`, `test_formato.py`, `test_inventario.py`, `test_schemas.py`
  — pure rules, no database.
- `test_ui_model.py` — the Qt model, proxy and delegates, with a persistence
  double and `QT_QPA_PLATFORM=offscreen`.
- `test_repositories.py`, `test_grid_integracion.py` — against PostgreSQL, inside a
  transaction that is rolled back.
- `test_views.py` — the screens, wired to an in-memory service.

## Design notes

The palette is measured, not chosen by eye: navy `#001E5E`, accent red `#FB0315`,
and every pair used in the interface clears WCAG AA. Two failures are documented
because they are easy to reintroduce: the accent red fails as text (4.10:1) and the
light grey `#9AA4B2` fails as a control border (2.52:1).
