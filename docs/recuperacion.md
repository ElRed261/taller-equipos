# Respaldos y recuperación

Qué se respalda, cómo se restaura y quién lo hace. Si estás leyendo esto durante
un incidente, andá directo a **Restaurar**, abajo.

## Qué hay

| Pieza | Dónde |
| --- | --- |
| Script de respaldo lógico | `scripts/respaldar.sh` |
| Script de respaldo base (PITR) | `scripts/respaldar_base.sh` |
| Volcados | `TALLER_RESPALDOS` (por defecto `~/respaldos-taller`) |
| Registro de cada corrida | `<destino>/registro.log` |
| Resumen del momento | `<destino>/taller-<fecha>.txt` (conteos de movimientos y catálogos) |

El volcado es de formato `custom` (`-Fc`): se restaura entero o por partes.
Se escribe en un archivo temporal y recién al final se renombra, así que un
respaldo con nombre definitivo siempre está completo y verificado con
`pg_restore --list`. Si algo falla, no queda un archivo a medias con nombre de
bueno y el script sale con código distinto de cero.

`--no-owner --no-privileges` se guarda a propósito: permite restaurar con otro rol
sin pelearse por los dueños de los objetos.

## Respaldar

```bash
scripts/respaldar.sh              # respalda
scripts/respaldar.sh --verificar  # respalda y prueba la restauración
```

Variables:

| Variable | Por defecto | Para qué |
| --- | --- | --- |
| `TALLER_RESPALDOS` | `~/respaldos-taller` | carpeta destino |
| `TALLER_RETENCION_DIAS` | `30` | antigüedad a partir de la cual se borra |
| `TALLER_DATABASE_URL` | lee `.env` | a qué base conectarse |

## Cifrado

Los volcados tienen nombres de personas y de departamentos: si salen del servidor,
van cifrados. Dos formas, elegí una:

**Destinatario (recomendado).** El servidor solo tiene la clave **pública**: si
alguien entra a la máquina no puede leer sus propios respaldos.

```bash
# donde vive la clave privada, no en el servidor
gpg --full-generate-key
gpg --export --armor admin@ejemplo > respaldo-publica.asc

# en el servidor
gpg --import respaldo-publica.asc
export TALLER_RESPALDO_GPG_RECIPIENTE=admin@ejemplo
```

**Clave simétrica.** Más simple, pero quien lea el archivo de la clave abre todos
los respaldos, así que ese archivo no puede vivir en el mismo servidor.

```bash
printf '%s\n' 'una frase larga y única' > /etc/taller/clave-respaldo
chmod 600 /etc/taller/clave-respaldo
export TALLER_RESPALDO_CLAVE=/etc/taller/clave-respaldo
```

El script **se niega a correr** si ese archivo tiene permisos abiertos (644), y
avisa en la salida y en el registro cuando no hay cifrado configurado. Con clave
simétrica además comprueba que el archivo cifrado se descifra y sigue siendo un
volcado válido: un respaldo cifrado que no se puede abrir es peor que no tenerlo.

Restaurar desde un archivo cifrado:

```bash
gpg --decrypt respaldo.dump.gpg > /tmp/respaldo.dump
pg_restore --no-owner --no-privileges -d taller_dev /tmp/respaldo.dump
rm -f /tmp/respaldo.dump
```

## Fuera del servidor

Un disco que se lleva la base se lleva también la carpeta de respaldos si están en
la misma máquina. El destino tiene que salir:

```bash
# destino externo con rsync, o el cliente de tu servicio de copias
rsync -az --delete -e ssh ~/respaldos-taller/ copias@otro-equipo:/respaldos/taller/
```

Y la clave privada de cifrado **nunca** en el servidor: si el servidor se pierde y
la clave estaba ahí, los respaldos se pierden con él.

## Automático

En un servidor Linux, con cron:

```cron
# /etc/cron.d/taller-respaldo
30 2 * * *  taller  cd /opt/taller-equipos && TALLER_RESPALDOS=/var/backups/taller scripts/respaldar.sh >> /var/log/taller-respaldo.log 2>&1
```

Con systemd, que es más fácil de revisar cuando algo falla:

```ini
# /etc/systemd/system/taller-respaldo.service
[Unit]
Description=Respaldo de la base del taller

[Service]
Type=oneshot
User=taller
WorkingDirectory=/opt/taller-equipos
Environment=TALLER_RESPALDOS=/var/backups/taller
ExecStart=/opt/taller-equipos/scripts/respaldar.sh
```

```ini
# /etc/systemd/system/taller-respaldo.timer
[Unit]
Description=Respaldo diario del taller

[Timer]
OnCalendar=*-*-* 02:30:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl enable --now taller-respaldo.timer
```

Y una vez por mes, la prueba de restauración, que es la que de verdad decide si
esto sirve:

```cron
0 4 1 * *  taller  cd /opt/taller-equipos && scripts/respaldar.sh --verificar
```

## Restaurar

**Escenario: la base se corrompió o alguien borró datos que hay que recuperar.**

1. Avisar y cortar el uso. Dos personas escribiendo mientras se restaura producen
   una base a medias.

   ```bash
   # que nadie pueda conectarse mientras dure
   psql -d postgres -c "alter database taller_dev allow_connections false"
   ```

2. Elegir el respaldo. El registro dice qué contenía cada uno:

   ```bash
   ls -la ~/respaldos-taller/
   tail -20 ~/respaldos-taller/registro.log
   cat ~/respaldos-taller/taller-20261102-090037.txt
   ```

   El `.txt` del respaldo dice cuántos movimientos y cuántas áreas tenía en ese
   momento: sirve para saber cuánto se va a perder antes de decidir.

3. Guardar la base actual aunque esté mal, para no perder los datos posteriores al
   respaldo (muchas veces se pueden rescatar a mano):

   ```bash
   pg_dump -Fc -f /tmp/antes-de-restaurar.dump taller_dev
   ```

4. Renombrar la base rota y crear una limpia:

   ```bash
   psql -d postgres -c "alter database taller_dev rename to taller_roto_$(date +%Y%m%d)"
   psql -d postgres -c "create database taller_dev"
   ```

5. Restaurar:

   ```bash
   pg_restore --no-owner --no-privileges -d taller_dev ~/respaldos-taller/taller-20261102-090037.dump
   ```

6. Verificar antes de devolver el acceso:

   ```bash
   psql -d taller_dev -c "select count(*) from movimiento"
   psql -d taller_dev -c "select count(*) from auditoria_edicion"
   psql -d taller_dev -c "select count(*) from movimiento where fecha_salida is not null"
   ```

   El conteo tiene que coincidir con el `.txt` de ese respaldo. Si no coincide,
   **no devuelvas el acceso**: algo falta.

7. Devolver el acceso y avisar.

   ```bash
   psql -d postgres -c "alter database taller_dev allow_connections true"
   ```

8. Cuando estés seguro de que no hace falta nada de la base vieja, borrarla. No
   antes: el paso 3 guardó el estado posterior, pero la base renombrada tiene los
   índices y secuencias originales.

**Escenario: hay que recuperar un solo registro borrado.**

No hace falta restaurar nada. `movimiento_eliminado` guarda el registro completo en
JSON al momento de borrarlo:

```sql
select id_original, usuario, eliminado_en, datos
from movimiento_eliminado
order by eliminado_en desc
limit 10;
```

Se reinserta a mano con los valores de ese JSON.

## PITR: recuperar a un minuto exacto

El respaldo lógico pierde todo lo posterior a él: si el respaldo es de las 2:30 y
alguien borra datos a las 15:00, se pierden casi trece horas. Para no perderlas
hacen falta **dos cosas juntas**, y una sin la otra no sirve:

1. **WAL archivados** de forma continua (`archive_mode = on`), y
2. **un respaldo base** físico desde el cual empezar a aplicarlos.

Los WAL sin respaldo base no se pueden aplicar; el respaldo base sin WAL solo
devuelve el estado de ese día.

### Configuración del servidor

```text
# postgresql.conf (archive_mode necesita reinicio, no alcanza con reload)
wal_level = replica
archive_mode = on
archive_command = 'test ! -f /var/lib/postgresql/wal-archive/%f && cp %p /var/lib/postgresql/wal-archive/%f'
archive_timeout = '5min'
```

`test ! -f` hace el comando idempotente: si el archivo ya está, no falla. Un
`archive_command` que falla no detiene la base, pero **el disco se llena de WAL**;
vigilá `pg_stat_archiver.failed_count`:

```sql
select archived_count, failed_count, last_failed_wal, last_archived_time
from pg_stat_archiver;
```

### Respaldo base

```bash
scripts/respaldar_base.sh          # usa pg_basebackup --format=plain y lo verifica
```

Va con `pg_verifybackup`, que compara cada archivo con el manifiesto que escribió el
servidor: un respaldo base sin verificar no sirve como punto de partida. Se toma una
vez por semana, y **siempre después de cambios grandes** (una migración, una
importación).

### Recuperar a un instante

Este procedimiento se ejecutó y se comprobó: recuperó 568 movimientos con 119 áreas
y dejó afuera, correctamente, una fila insertada justo después del instante elegido.

1. Elegir el instante. Con el registro de la aplicación a mano, o el log del
   servidor. En el ejemplo: `2026-11-02 09:06:02`.

2. Descomprimir el base (y descifrarlo si hace falta) en una carpeta vacía:

   ```bash
   gpg --decrypt base-20261102-090540.tar.gz.gpg | tar -xzf - -C /tmp
   mv /tmp/.base-20261102-090540.parcial /tmp/pitr
   ```

3. Escribir el destino y el comando de restauración de WAL:

   ```bash
   cat >> /tmp/pitr/postgresql.auto.conf <<'EOF'
   restore_command = 'cp /var/lib/postgresql/wal-archive/%f %p'
   recovery_target_time = '2026-11-02 09:06:02'
   recovery_target_action = 'promote'
   EOF
   touch /tmp/pitr/recovery.signal
   ```

4. Levantarlo en otro puerto, sin tocar el de producción:

   ```bash
   pg_ctl -D /tmp/pitr -o "-p 5433 -k /tmp -c listen_addresses=''" -l /tmp/pitr.log -w start
   ```

5. Mirar el registro: tiene que decir a qué altura se detuvo.

   ```bash
   grep -E "recovery stopping|redo done|ready to accept" /tmp/pitr.log
   ```

   Si dice `recovery ended before configured recovery target was reached`, el
   instante pedido es más nuevo que el último WAL archivado: hay que archivar más
   o elegir un instante anterior.

6. Verificar los datos **antes** de reemplazar nada:

   ```bash
   psql -h /tmp -p 5433 -d taller_dev -c "select count(*) from movimiento"
   psql -h /tmp -p 5433 -d taller_dev -c "select count(*) from area"
   ```

7. Recién entonces reemplazar el directorio de datos de producción, con la base
   detenida y guardando el anterior:

   ```bash
   scripts/bd.sh stop
   mv /var/lib/postgresql/18 /var/lib/postgresql/18.roto-$(date +%Y%m%d)
   mv /tmp/pitr /var/lib/postgresql/18
   rm -f /var/lib/postgresql/18/recovery.signal
   scripts/bd.sh start
   ```

8. Comprobar que `archive_mode` sigue en `on` y que `pg_stat_archiver` no acumula
   fallos.

## Lo que sigue faltando

- **Programar todo esto en el servidor definitivo**: los cron están escritos acá,
  no instalados. Es lo único que separa estas piezas de estar realmente cubierto.
- **Copia fuera del servidor**: documentada, no automatizada.
- **Probar la restauración una vez por mes**: `scripts/respaldar.sh --verificar` en
  cron. La verificación ya se ejecutó y coincidió, pero tiene que repetirse o deja
  de ser cierta.
