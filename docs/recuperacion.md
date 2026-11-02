# Respaldos y recuperación

Qué se respalda, cómo se restaura y quién lo hace. Si estás leyendo esto durante
un incidente, andá directo a **Restaurar**, abajo.

## Qué hay

| Pieza | Dónde |
| --- | --- |
| Script de respaldo | `scripts/respaldar.sh` |
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

## Lo que falta para estar cubierto del todo

- **Pérdida del día en curso**: el respaldo diario pierde todo lo posterior al
  último. Para eso hace falta archivar los WAL (`archive_mode = on`), que permite
  restaurar al minuto exacto. Está como T5 en
  `odd/tasks/seguridad-base-de-datos.md`.
- **Cifrado**: los volcados tienen nombres de personas. Si salen del servidor,
  cifrarlos (T5).
- **Copia fuera del servidor**: un disco que se lleva la base se lleva también la
  carpeta de respaldos si están en la misma máquina. Copiar el destino a otro
  equipo o a un servicio externo.
- **La clave de cifrado, si no está en el servidor**: si se cifra y la clave vive
  en el mismo servidor, no protege de nada.
