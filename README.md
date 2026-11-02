<div align="center">
  <img src="docs/banner.svg" alt="Taller de equipos" width="100%">
</div>

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Qt](https://img.shields.io/badge/Qt-6.12-41CD52?style=flat-square&logo=qt&logoColor=white)](https://www.qt.io/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![License](https://img.shields.io/badge/license-MIT-001E5E?style=flat-square)](LICENSE)

**A desktop application that records the intake and dispatch of IT equipment in a
workshop, replacing a legacy `.NET WinForms` export with a normalized database and a
client several technicians share over the local network.**

</div>

---

## The problem

The workshop kept its history in a text file exported from a `DataGridView`. The
first column held `System.Drawing.Bitmap` — the icon cell, not a status. Department
names were typed 191 different ways, technicians appeared under 38 spellings, dates
were occasionally reversed, and inventory codes mixed the letter `O` with the digit
`0`.

This project imports those 568 rows **without guessing**, then prevents the same
mess from coming back: the app offers catalogs instead of free text, derives the
status instead of storing it, and lets the database reject what the interface should
never have produced.

<div align="center">
  <img src="docs/capturas/formulario.png" alt="Entry form" width="90%">
</div>

## Features

**Data integrity**
- Status (dispatched / in the workshop / no data) is **derived** from the departure
  date, never stored, so it cannot desynchronise.
- Business dates are `DATE`: every timestamp in the legacy file was midnight, so a
  `TIMESTAMPTZ` would promise precision the data does not have.
- A `CHECK` rejects a departure earlier than the intake. The only escape hatch is a
  flag that imported rows alone may carry.
- Inventory codes normalise to their canonical five digits and keep leading zeros.

**Daily use**
- Fast keyboard entry: `Ctrl+Enter` saves and leaves the form ready for the next unit.
- Double click opens the full record instead of editing one cell at a time.
- Search ignores accents and case, and requires every word: `dvd agromet` finds the
  DVD drive from the Agrometeorology department.
- One click dispatches a unit; the button only enables "mark as reviewed" when the
  dates are consistent.
- CSV export of exactly what the filters are showing, formatted for Excel in a
  Spanish locale (semicolon, UTF-8 BOM, `dd/mm/aaaa`).
- The list is ordered by work, not by alphabet: rows flagged for review, or missing
  the date, the department or the inventory code, sink to the bottom. With 568 rows
  those are the ones that get lost.

**Administration**
- Catalogs for equipment types, departments and technicians: create, rename,
  deactivate, reactivate and **merge duplicates**, showing how many records move
  before anything changes.
- An admin mode that deletes a whole record, requiring the equipment code typed as
  confirmation, and keeping a snapshot of what was deleted.
- Field-level audit trail: who changed what, with the previous and new value.
- Accounts with argon2id passwords, so the "who" in the audit trail is a verified
  session and not a name typed at the door. The login can be **switched off** in
  Configuration for a single-operator machine; the accounts and the audit stay, and
  the status bar then says `sin ingreso` so an unverified session never looks like a
  verified one.
- Every catalog change (create, rename, activate, deactivate, merge) is recorded with
  its author and readable in Configuration → Historial. Merging two departments
  leaves two rows: where it went and how many records moved.

## Install

The application sets itself up the first time it runs: it asks for the
organisation's name and logo and for the database connection, and creates the
tables from the setup window. Nothing has to be edited by hand.

Before the first window it asks for an account: the first one is the administrator
and creates the others from Configuration → Usuarios. On a machine with a single
operator that dialog can be switched off, and the application then opens directly
with the default account.

Then it remembers everything in your user configuration folder, so the second run
opens straight into the app.

For development, the environment variables and a `.env` file keep working and take
precedence over what the setup window saved.

## Quick start

Requires PostgreSQL 18 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env          # point TALLER_DATABASE_URL at your database
uv run alembic upgrade head
./.venv/bin/python -m taller.main
```

Setting `TALLER_CONFIG_DIR` points the application at another configuration folder,
which is what the tests use.

The interface is in Spanish, which is the language of its users. The code,
comments and documentation are in English.

## Architecture

```text
src/taller/
  main.py            entry point: user, connection guard, window
  servicios.py       the only seam between widgets and the database
  database/          models, repositories, connection
  schemas/           Pydantic: the validation boundary
  inventario.py      inventory-code rules, one definition for three callers
  seguridad.py       password hashing and the rules for accepting one
  arranque.py        startup configuration: brand, connection, login switch
  etl/               one-shot import of the legacy export
  ui/                theme, icons, models, delegates, views
```

Three rules hold the layering together: repositories **never commit** (the caller
owns the transaction), they return **DTOs and never ORM instances** (a detached
object crossing a Qt thread is a bug waiting to happen), and there is **one session
per operation**.

Read [`docs/arquitectura.md`](docs/arquitectura.md) for the schema, the import
rules and the colour decisions.

## Testing

```bash
./.venv/bin/python -m pytest
```

> Use `./.venv/bin/python -m pytest` rather than `pytest`: a wrapper on `PATH` in
> some environments swallows the report and prints "No tests collected" while the
> tests actually ran.

380 tests. The suites split by what they need: pure rules with no database, the Qt
model with a persistence double and `QT_QPA_PLATFORM=offscreen`, and the repositories
against a real PostgreSQL inside a transaction that is rolled back.

Two habits the suite learned the hard way: a test that asserts a hardcoded row count
breaks the day the workshop dispatches a real unit, so assertions compare against the
database instead; and a test that passes only through a persistence double can hide a
missing method in the real service, so the new screens are also exercised against a
real service.

## Security and backups

```bash
uv run python scripts/verificar_seguridad_bd.py   # audits roles, network, TLS
scripts/respaldar.sh --verificar                  # dumps, encrypts, tests a restore
scripts/respaldar_base.sh                         # base backup for PITR
```

The application connects with a role that is not a superuser, over TLS, with
`scram-sha-256` passwords. Backups are encrypted (a public key on the server, the
private one off it), verified with `pg_restore --list` before being renamed, and the
restore is rehearsed rather than described: the script restores into a throwaway
database and compares row counts.

[`docs/seguridad.md`](docs/seguridad.md) explains what protects the data and what is
still missing. [`docs/recuperacion.md`](docs/recuperacion.md) is the procedure to
follow the day something breaks, including point-in-time recovery.

## Packaging

```bash
scripts/empaquetar.sh
```

Builds `dist/taller-equipos/` with PyInstaller — a directory, not a single file, so
the window appears instantly instead of unpacking Qt into a temporary folder on every
start. The binary needs no Python installed and answers `--version` for support.

## License

MIT — see [LICENSE](LICENSE).
