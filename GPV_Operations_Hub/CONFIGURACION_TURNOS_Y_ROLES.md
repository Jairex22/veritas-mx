# Configuración de turnos, grupos y roles

## Turnos y descansos

*Administración › Turnos* (código, nombre, inicio, fin). Si **fin ≤ inicio** el turno cruza la
medianoche (p. ej. 22:00–06:00) y su fecha operativa es la del **inicio**. Los descansos se dan de
alta en *Administración técnica › Portal del turno › Descansos*; se descuentan del tiempo planeado.
Turno específico del piloto: **POR CONFIRMAR**. Zona horaria: America/Mexico_City.

## Roles (capacidades del portal del turno)

| Capacidad | Admin | Supervisor | Ingeniero | Técnico | Operador |
|---|:-:|:-:|:-:|:-:|:-:|
| `shift.use` · Mi turno, ayuda, paros, materiales, calidad (observación), relevo | ✔ | ✔ | ✔ | ✔ | ✔ |
| `shift.capture` · captura manual de contingencia (queda provisional) | ✔ | ✔ | ✔ | ✔ | ✔ |
| `shift.attend` · atender ayudas/materiales de sus áreas, tablero | ✔ | ✔ | ✔ | ✔ | |
| `shift.plan` · metas del turno | ✔ | ✔ | | | |
| `shift.reconcile` · conciliación de capturas manuales | ✔ | ✔ | | | |
| `shift.close` · revisar y cerrar reportes del turno | ✔ | ✔ | | | |
| `shift.quality` · disposición de observaciones de calidad | ✔ | ✔ | | | |
| `shift.configure` · líneas, estaciones, motivos, OData del turno | ✔ | | | | |
| `flx.status` · FactoryLogix: estado de conexión y catálogo | ✔ | ✔ | ✔ | ✔ | |
| `flx.query` · FactoryLogix: consultas controladas de solo lectura | ✔ | ✔ | ✔ | | |
| `flx.admin` · FactoryLogix: diagnóstico, esquema y sondeo controlado | ✔ | | | | |

El rol **Técnico** (2.0) tiene todo lo del Operador más atender solicitudes, resolver incidencias y
ver el estado de FactoryLogix.

Las capacidades se ajustan por rol en *Administración › Permisos* (queda en bitácora). Todas se
verifican en el servidor; ocultar un botón nunca es el único control. Además, cada persona solo ve
las **áreas** asignadas en su perfil.

## Grupos de atención (roles combinados)

Los grupos de Django (*Administración técnica › Grupos*) representan equipos: Mantenimiento,
Calidad, Materiales, Ingeniería de procesos, Pruebas, Supervisión (nombres de ejemplo, POR CONFIRMAR).
Una persona puede estar en varios grupos (p. ej. un ingeniero que también atiende Mantenimiento);
el portal suma las vistas de todos sus grupos. Cada **motivo de ayuda** define:

* grupo que recibe la solicitud;
* minutos para recordatorio si nadie la recibe;
* minutos para escalar (y grupo de escalamiento);
* si requiere verificación por alguien distinto de quien resolvió.

Recordatorios y escalamientos son **notificaciones internas** del portal. No se envían correos ni
mensajes externos: eso requeriría un alcance definido expresamente y está desactivado.

## Líneas y estaciones

*Administración técnica › Portal del turno › Líneas*: sitio, área, código, piloto, unidad de
conteo, factor de panelización (y si está **confirmado**), plantillas de etiqueta del operador y
sus estaciones (código/operación como en FactoryLogix, lado Top/Bottom, secuencia, operación de
conteo). Cada estación tiene un token QR propio (`/turno/estacion/<token>/`).

Todo cambio de configuración queda en el historial del administrador técnico y en la bitácora de
auditoría del portal.
