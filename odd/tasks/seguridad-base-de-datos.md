# Protección de la base de datos y de la auditoría

Cerrar las brechas de seguridad del sistema en producción: rol de base acotado,
respaldos que se puedan restaurar, identidad real de quien edita y rastro de los
cambios de catálogo.

Origen: pedido del usuario del 2026-11-02 y el análisis de `docs/seguridad.md`.
Estado: plan aprobado para aplicar; nada de esto está implementado todavía.

## Specs

**S1 — Rol de base acotado.** El usuario escribió: *"hay que proteger la base de
datos a Full, debemos tener mecanismos, ¿cuáles recomiendas?"*. La aplicación no se
conecta como superusuario. Existe un rol de aplicación dueño de su base, sin
`SUPERUSER`, sin `CREATEDB` y sin `CREATEROLE`, y `pg_hba.conf` autoriza por base y
por rol, no `host all all`.

**S2 — Respaldos automáticos y restauración probada.** Un respaldo diario
automático con retención, y un procedimiento de restauración que se ejecuta de
verdad al menos una vez antes de declarar el sistema seguro. Un respaldo que nunca
se restauró no cuenta como respaldo.

**S3 — Identidad real de quien edita.** El usuario escribió: *"la auditoría no vale
si cualquiera escribe su nombre"*. Hoy el programa pregunta quién sos y acepta
cualquier texto. La aplicación autentica al usuario contra la tabla `usuario` con
contraseña hasheada, y `auditoria_edicion.usuario_etiqueta` deja de ser una
declaración libre.

**S4 — Rastro de los cambios de catálogo.** Crear, renombrar, desactivar, reactivar
y fusionar un área, un tipo de equipo o un técnico queda registrado con quién,
cuándo, qué valor había y qué valor quedó. Evidencia de la falta: durante el
desarrollo aparecieron cuatro técnicos desactivados sin ningún rastro de autor.

**S5 — Los respaldos no se leen si salen del servidor.** Los volcados contienen
nombres de personas y de departamentos; se cifran antes de moverse fuera del
servidor.

**S6 — Recuperación escrita.** Existe un procedimiento con pasos, responsable y
tiempo estimado para restaurar el servicio, y no depende de la memoria de una sola
persona.

## Tasks

| ID | S# | Entrega | Ruta | Commit |
| --- | --- | --- | --- | --- |
| T1 | S1 | Rol `taller_app` con permisos mínimos, `pg_hba` por base y rol, `listen_addresses` en la interfaz interna; el asistente y el README dejan de sugerir `postgres` | inline | `630815b` |
| T2 | S2,S6 | `scripts/respaldar.sh` (volcado, retención, registro) + unidad de cron/systemd + `docs/recuperacion.md` con el procedimiento y una prueba de restauración ejecutada | inline | `—` |
| T3 | S3 | Tabla `usuario` con `password_hash` (argon2), pantalla de alta de contraseña, login al arrancar, `usuario_id` en la auditoría, migración y pruebas | worker | — |
| T4 | S4 | Tabla `auditoria_catalogo`, escritura en los cinco caminos del `CatalogoRepository`, vista en Configuración y pruebas | worker | — |
| T5 | S5 | Cifrado de los volcados antes de salir del servidor y destino externo documentado | inline | — |
| T6 | S1 | TLS (`sslmode`) y firewall del servidor, con la decisión documentada | inline | — |

## Detalle por tarea

**T1 · Rol y red** (media tarde, riesgo alto si se hace mal: deja la aplicación sin
conexión). Crear el rol, transferir la propiedad de la base, verificar que el
superusuario ya no es el que usa la app, y que `taller_ro` sigue leyendo sin poder
escribir. Aceptación: la app conecta y opera con `taller_app`; `taller_app` recibe
`permission denied` al intentar `CREATE ROLE`; la suite completa pasa.

**T2 · Respaldos** (media tarde). Aceptación: el script corre desde cron, deja un
archivo con fecha, borra lo que pasa de la retención y devuelve código distinto de
cero si el volcado falla. La restauración de prueba se ejecuta y el conteo de
movimientos coincide con producción.

**T3 · Login real** (la más grande; conviene delegarla). Decisiones abiertas abajo.
Aceptación: sin contraseña correcta no se entra; la auditoría registra el usuario
autenticado y no lo que se escriba en un campo; una contraseña no se guarda nunca en
claro ni aparece en un log; las pruebas cubren alta, login correcto, login fallido y
usuario desactivado.

**T4 · Auditoría de catálogo** (un día). Aceptación: cada una de las cinco acciones
deja una fila con valor anterior y nuevo; fusionar dos filas deja constancia de las
dos; la vista muestra el historial de un área ordenado por fecha.

**T5 · Cifrado** (una hora). Aceptación: un volcado cifrado no se puede abrir sin la
clave; la clave no vive en el servidor.

**T6 · TLS y firewall** (una hora, depende del servidor). Aceptación: la conexión
sin TLS desde fuera del servidor falla si se decidió exigirlo; el puerto 5432 solo
responde a las direcciones del taller.

## Orden recomendado

T1 y T2 primero: son una tarde, no tocan código de la aplicación y cierran los dos
riesgos que pueden costar la base entera. Después T3, que es la brecha de auditoría
y la única que cambia el comportamiento diario. T4 en paralelo a T3 si hay dos
personas. T5 y T6 cuando el servidor esté definido.

## Decisiones abiertas

1. **¿Contraseña propia o identidad del sistema operativo?** Con contraseña propia la
   app es portable a cualquier PC; con identidad de Windows no hay nada que recordar
   pero se depende del dominio.
2. **¿argon2 o bcrypt?** argon2 es la recomendación actual; bcrypt está disponible en
   más entornos. Hay que elegir uno y fijarlo en las dependencias.
3. **¿Quién administra los usuarios?** El modo administrador ya existe para borrar
   registros; dar de alta usuarios y resetear contraseñas es otra capacidad y merece
   su propia confirmación.
4. **¿TLS obligatorio o no?** Depende de si la red del taller es conmutada y de
   confianza. Hay que decidirlo y escribirlo.

## Log

**L1** — Pedido del usuario el 2026-11-02, textual: *"Otra cosa es que hay que
proteger la base de datos a Full, debemos tener mecanismos, cuáles recomiendas."* y
luego: *"Genera un plan de implementación para esto y guardalo en odd para aplicarlo
luego."*

**L2** — Relevamiento del estado al momento de escribir el plan. Ya existen:
integridad por `CHECK` y claves foráneas `RESTRICT`; estado derivado en
`v_movimiento_estado`; auditoría por campo en `auditoria_edicion`; constancia de
borrados en `movimiento_eliminado`; roles `taller` (aplicación) y `taller_ro` (solo
lectura, sin contraseña en loopback); contraseñas fuera de git; `config.json` con
permisos `0600`. Faltan los seis puntos de las specs.

**L3** — Evidencia de S4: en la sesión del 2026-10-30 aparecieron cuatro técnicos
desactivados (Angel Davis, Eliezer Medina, Wagner Junior, Yolanda Yohana) sin ningún
registro de autor ni de momento, porque `auditoria_edicion` solo cubre movimientos.

**L4** — Evidencia de S3: `main.py` pide el nombre con `QInputDialog` y acepta
cualquier texto; `auditoria_edicion.usuario_etiqueta` guarda esa declaración. La
columna dice quién *dice* la aplicación que actuó, no quién actuó.

**L5** — T1 aplicado el 2026-11-02. Medido antes de tocar: el rol `taller` ya era
`NOSUPERUSER NOCREATEDB NOCREATEROLE`, `taller_ro` solo tenía `SELECT`, y
`password_encryption` ya era `scram-sha-256`. El hueco real estaba en `pg_hba.conf`:
`local all all trust` dejaba que cualquier proceso local entrara como cualquier rol,
incluido el superusuario `stward`, sin contraseña. Pasó a `peer`; verificado que
`psql` como `stward` sigue entrando, que `taller` por socket ahora se rechaza, que la
aplicación sigue conectando por TCP con scram y que las 288 pruebas seguían verdes.
Se agregó `scripts/verificar_seguridad_bd.py` (17 pruebas) que audita privilegios del
rol, cifrado de contraseñas, reglas de red, interfaces, TLS y escritura del rol de
solo lectura, con código de salida. Decisión: el nombre del rol no importa
(`taller` acá, `taller_app` en una instalación nueva); lo que importa son los
atributos, y eso es lo que verifica el auditor.

**L6** — T2 aplicado el 2026-11-02. `scripts/respaldar.sh` vuelca en formato
`custom` con `--no-owner --no-privileges`, escribe a un temporal, verifica con
`pg_restore --list` y solo entonces renombra; borra el temporal si algo falla y sale
distinto de cero. Restauración probada de verdad el mismo día: 568 movimientos y 559
registros de auditoría coincidieron. Dos defectos encontrados al probarlo y
corregidos: `pg_restore` recibía a la vez una cadena de conexión y un archivo y
restauraba en el lugar equivocado, y dos corridas dentro del mismo segundo se pisaban
(el nombre ahora lleva sufijo). `docs/recuperacion.md` tiene el procedimiento con los
pasos de corte, respaldo previo del estado malo y verificación de conteos.

**L7** — El repositorio dejó de versionar la especificación interna al hacerse
público (2026-10-30); este documento es el primero desde entonces y no contiene
datos institucionales ni nombres de personas.
