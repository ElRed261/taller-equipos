# Proteger la base de datos

Qué protege hoy al sistema, qué falta, y en qué orden hacerlo. Está escrito para
esta instalación concreta: PostgreSQL 18 en un servidor de la red local, un cliente
de escritorio y datos institucionales que no se pueden perder ni reescribir sin
dejar rastro.

## Lo que ya está

| Mecanismo | Dónde |
| --- | --- |
| Integridad de fechas y claves foráneas `RESTRICT` | `CHECK` y FKs del esquema |
| Estado derivado, no almacenado | vista `v_movimiento_estado` |
| Auditoría por campo, con valor anterior y nuevo | `auditoria_edicion` |
| Constancia de cada registro borrado | `movimiento_eliminado` |
| Rol de aplicación y rol de solo lectura separados | `taller` y `taller_ro` |
| Contraseñas fuera de git | `.env`, `branding.json` y `marca-local/` ignorados |
| Configuración del instalador solo para el dueño | `chmod 600` en `config.json` |
| Ediciones atribuidas a un usuario | `auditoria_edicion.usuario_etiqueta` |
| Acceso local sin contraseña cerrado | `pg_hba.conf`: `local` en `peer`, no en `trust` |
| Auditoría de estas reglas, con código de salida | `scripts/verificar_seguridad_bd.py` |
| Respaldo verificado y restauración probada | `scripts/respaldar.sh`, `docs/recuperacion.md` |
| Respaldo cifrado y respaldo base para PITR | `scripts/respaldar.sh`, `scripts/respaldar_base.sh` |
| Contraseñas con argon2id y login obligatorio | tabla `usuario`, `src/taller/seguridad.py` |
| Rastro de todo cambio de catálogo | tabla `auditoria_catalogo`, pestaña Historial |
| TLS en la conexión con la base | `ssl = on`, `sslmode=require` |

## Prioridad 0 — antes de ponerlo en producción

### 1. La aplicación no debe conectarse como superusuario

El asistente ofrece `postgres` por comodidad, y eso es un superusuario: puede
borrar la base entera, leer cualquier tabla y desactivar restricciones. Un error de
la aplicación con ese rol no tiene freno.

Creá un rol para la aplicación y usá ese:

```sql
CREATE ROLE taller_app LOGIN PASSWORD 'una-clave-larga-y-unica';
CREATE DATABASE taller_dev OWNER taller_app;
-- Lectura para herramientas (el MCP, por ejemplo)
CREATE ROLE taller_ro LOGIN PASSWORD 'otra-clave';
GRANT CONNECT ON DATABASE taller_dev TO taller_ro;
GRANT USAGE ON SCHEMA public TO taller_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO taller_ro;
```

El asistente pide el usuario de base de datos: ahí va `taller_app`, nunca `postgres`.

### 2. Reglas de red, no `host all all`

`pg_hba.conf` debe nombrar base y rol, y aceptar solo las direcciones del taller:

```text
# /etc/postgresql/…/pg_hba.conf
host    taller_dev    taller_app    192.168.1.0/24    scram-sha-256
host    taller_dev    taller_ro     127.0.0.1/32      trust
```

Y en `postgresql.conf`, escuchar solo la interfaz interna:

```text
listen_addresses = '192.168.1.10'
```

Nunca `0.0.0.0` en una máquina con salida a internet.

### 3. Respaldos automáticos, y una restauración probada

**Hecho**: `scripts/respaldar.sh` vuelca, verifica el archivo con `pg_restore
--list`, escribe la línea de registro y borra lo que pasa de la retención.
`scripts/respaldar.sh --verificar` restaura en una base descartable y compara los
conteos; ya se ejecutó una vez y coincidió (568 movimientos, 559 registros de
auditoría). Falta programarlo en el servidor: ver `docs/recuperacion.md`.

Un respaldo que nunca se restauró no es un respaldo. Dos piezas:

```bash
# /etc/cron.d/taller-backup
30 2 * * *  postgres  pg_dump -Fc taller_dev | gzip > /var/backups/taller/$(date +\%F).dump.gz
```

```bash
# retención: 30 días
find /var/backups/taller -name '*.dump.gz' -mtime +30 -delete
```

Y una vez por mes, en una base desechable:

```bash
createdb prueba_restauracion
pg_restore -d prueba_restauracion /var/backups/taller/2026-10-30.dump.gz
psql -d prueba_restauracion -c 'select count(*) from movimiento'
dropdb prueba_restauracion
```

Si ese `count` no coincide con producción, el respaldo no sirve y hay que saberlo
antes del incidente, no después.

## Cómo verificar que sigue así

```bash
uv run python scripts/verificar_seguridad_bd.py
```

Dice `OK`, `AVISO` o `FALLA` por cada control, con el comando que lo arregla, y
sale con código distinto de cero si hay algo que arreglar. Como el rol de la
aplicación no puede leer `pg_hba_file_rules` (y está bien que no pueda), esa parte
se revisa aparte:

```bash
uv run python scripts/verificar_seguridad_bd.py --admin-url "postgresql+psycopg://.../taller_dev"
```

Conviene correrlo después de cada cambio de infraestructura y antes de entregar el
sistema a alguien más.

## Prioridad 1 — la semana siguiente

### 4. La auditoría no sirve si cualquiera elige su nombre

**Hecho.** El programa ya no pregunta "¿quién sos?": pide usuario y contraseña, y la
compara contra la tabla `usuario` con argon2id. Al arrancar sin ninguna cuenta
administradora se crea la primera, y esa cuenta da de alta a las demás desde
Configuración → Usuarios.

Tres decisiones que hacen esto defendible:

- **Un solo mensaje de error** para usuario inexistente y contraseña equivocada: dos
  mensajes distintos convierten el login en un buscador de usuarios.
- **Sin atajos**: se quitó `TALLER_USUARIO`, que elegía la identidad por variable de
  entorno. Un atajo así anula la auditoría entera.
- **Regla de contraseña solo por largo** (12 caracteres). Las reglas de mayúsculas y
  símbolos empujan a la gente a contraseñas cortas y predecibles.

Lo que queda: **no hay bloqueo por intentos fallidos**. Si te importa la fuerza
bruta desde la red, agregalo; con la base en una LAN cerrada no es lo primero.

### 5. Auditar los catálogos

**Hecho.** La tabla `auditoria_catalogo` registra cada alta, renombrado, activación,
desactivación y fusión, con el valor anterior, el nuevo, quién y cuándo. Se lee en
Configuración → Historial.

Una fusión deja dos filas: a dónde se movió y cuántas referencias se movieron. Sin
eso, fusionar dos áreas es indistinguible de borrar una.

### 6. Cifrar los respaldos

Los dumps contienen nombres de personas y de departamentos. Si salen del servidor
en un pendrive o a un servicio en la nube:

```bash
pg_dump -Fc taller_dev | gpg --encrypt --recipient admin@ejemplo | gzip > respaldo.gpg
```

Y guardá la clave privada fuera del servidor, o el cifrado no protege de nada.

### 7. Punto en el tiempo (PITR)

**Hecho** en el clúster de desarrollo: `archive_mode = on`, `wal_level = replica`,
`archive_timeout = 5min`, y `scripts/respaldar_base.sh` para el respaldo base. La
recuperación se ensayó de verdad y se detuvo en el instante pedido. Procedimiento en
`docs/recuperacion.md`. Falta programarlo en el servidor definitivo.

Un `pg_dump` diario pierde todo lo del día. Si perder un día de trabajo no es
aceptable:

```text
wal_level = replica
archive_mode = on
archive_command = 'test ! -f /var/lib/postgresql/wal/%f && cp %p /var/lib/postgresql/wal/%f'
```

Con los WAL archivados se restaura al minuto exacto anterior al incidente.

## Prioridad 2 — higiene

- **TLS** (`sslmode=require`) si la red del taller no es de confianza. En una LAN
  cerrada y conmutada es opcional; documentá la decisión.
- **Firewall** del servidor: solo 5432 desde las IP del taller, nada más.
- **Monitoreo**: `log_connections = on`, alerta cuando el disco pasa el 80 %.
- **Contraseñas en el llavero del sistema** en lugar de `config.json`. Hoy el
  archivo está en `0600`, que protege de otros usuarios de la máquina pero no de
  quien tenga acceso a tu sesión.
- **Un procedimiento escrito de recuperación**: quién restaura, desde qué respaldo,
  cuánto tarda y a quién se avisa.

## Lo que no recomiendo

- **Cifrar la base entera a nivel de disco como única defensa**: protege el equipo
  robado, no el acceso indebido desde la red.
- **Un usuario compartido por todo el taller con la misma contraseña de base**: es
  lo que hace que la auditoría no sirva.
- **Dar `SUPERUSER` al rol de la aplicación** "para que no falle nada": convierte
  cualquier error en una pérdida total.
- **Respaldos solo en el mismo servidor**: un disco que falla se lleva la base y los
  respaldos.
