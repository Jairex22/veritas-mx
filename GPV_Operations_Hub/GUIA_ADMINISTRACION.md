# Guía de administración · Portal del turno

## Inicio diario (equipo del piloto)

Doble clic en `INICIAR.bat`. Abre dos ventanas: el sitio (`127.0.0.1:8000`) y, minimizado,
«GPV servicio del turno» (sincronización OData, recordatorios, borradores de reporte). Ambas deben
quedar abiertas. El sitio **solo** escucha en `127.0.0.1`: no se modifica el firewall ni se expone a la red.

## Configuración inicial

1. *Administración › Áreas, Turnos, Usuarios* (perfil con área SMT y rol).
2. *Administración técnica* (`/django-admin/`) › Grupos: equipos de atención e integrantes.
3. *Portal del turno › Sitios, Líneas (con estaciones), Motivos de ayuda, Motivos de paro, Descansos,
   Listas de verificación, Instrucciones*.
4. *Mi turno › Metas* (supervisor): metas por línea, turno, fecha y orden.
5. *Mi turno › Fuentes*: conexión OData (ver `CONFIGURACION_ODATA.md`).

## Operación

| Tarea | Dónde |
|---|---|
| Ver estado de fuentes, sincronizaciones y lagunas | Mi turno › Fuentes |
| Revisar capturas manuales | Mi turno › Conciliación |
| Revisar/cerrar reportes, PDF y Excel | Mi turno › Cierre |
| Tablero de líneas, ayudas abiertas, reportes sin cerrar | Mi turno › Supervisión |
| Pantalla de piso | `/turno/pantalla/<código de línea>/` (pantalla completa del navegador, F11) |
| Bitácora | Administración › Auditoría |

## Comandos útiles (desde la carpeta con `manage.py`)

```bat
.venv\Scripts\python.exe manage.py run_shift_service --once
.venv\Scripts\python.exe manage.py seed_smt_pilot
.venv\Scripts\python.exe manage.py gpv_diagnose
.venv\Scripts\python.exe manage.py gpv_backup
```

`run_shift_service --once` ejecuta un ciclo (sincronización, recordatorios, borradores) y termina.
`seed_smt_pilot` carga la configuración de **ejemplo** (solo si `GPV_ALLOW_DEMO=true`).

## Responsables (POR CONFIRMAR por GPV)

| Rol | Responsabilidad | Persona | Reemplazo |
|---|---|---|---|
| Propietario del proceso (SMT) | Define operación de conteo, metas, motivos y criterios del reporte | POR CONFIRMAR | POR CONFIRMAR |
| Responsable técnico | Equipo del piloto, actualizaciones, respaldos, conexión OData | POR CONFIRMAR | POR CONFIRMAR |
| Soporte a usuarios | Altas, contraseñas, grupos, dudas de uso | POR CONFIRMAR | POR CONFIRMAR |
| Calidad | Disposiciones y referencia al registro oficial | POR CONFIRMAR | POR CONFIRMAR |

## Cambios que afectan cálculos

Operación de conteo, factor de panelización, turnos/descansos, metas y mapeo OData cambian cifras.
Cada cambio queda en el historial de la administración técnica y en la bitácora; los reportes ya
cerrados conservan su instantánea, y los datos tardíos crean una revisión nueva. Cambiar la conexión
o el mapeo OData desactiva la sincronización hasta un nuevo diagnóstico correcto.

## Crecimiento

Para uso permanente desde varias estaciones: servidor interno administrado por GPV, PostgreSQL 16,
Waitress detrás de HTTPS, `run_worker` y `run_scheduler` como servicios (ver `DESPLIEGUE_INTERNO.md`).
No es necesario para la primera prueba.
