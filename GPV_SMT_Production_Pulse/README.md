# GPV SMT Production Pulse — v1.1.0

**GPV Americas | SMT Production Pulse** — Monitoreo inteligente de productividad de SMT.

Aplicación local de solo lectura vinculada a FactoryLogix OData (`http://10.62.54.10:6065/odata/`,
entidad exclusiva **`ProductivityOverTime`**). Un **recolector automático** hace **una consulta
cada 300 s** mientras el servicio Python está en ejecución, aunque no haya navegadores abiertos, y
guarda los resultados en SQLite sin duplicados. El **Monitor** se actualiza solo leyendo la base local.

## Ejecutar en Windows 11 (sin administrador)

```bat
cd %USERPROFILE%\Apps\GPV_SMT_Production_Pulse
```

```bat
py app.py --live
```

Abrir **http://127.0.0.1:8765**. Detener con `Ctrl + C`.

Sin ventana de consola (sigue recolectando; registros en `logs\production_pulse.log`):

```bat
pyw app.py --live
```

Solo si el servidor exige autenticación Windows integrada (instalación por usuario):

```bat
py -m pip install --user -r requirements-windows-auth.txt
```

Modo demostración (servidor simulado, base de datos separada):

```bat
py app.py --demo
```

Pruebas automatizadas:

```bat
py -m unittest discover -s tests -v
```

Detalle completo, inicio automático al iniciar sesión y solución de problemas:
[docs/INSTALACION.md](docs/INSTALACION.md).

## Garantías de carga sobre FactoryLogix

* 1 solicitud OData por ciclo de 5 min en operación normal (mínimo configurable: 300 s).
* Validación al iniciar: 1 `$metadata` + máximo 8 pruebas `$top=1` (no se repiten mientras el servidor no responde).
* Siempre con filtro de fecha comprobado y `$top ≤ 50`; nunca se sigue `nextLink`; nunca se descarga la entidad completa.
* Un único recolector por equipo (lock del sistema operativo); los navegadores no generan consultas OData.
* Errores 401/500/timeout/desconexión: datos previos visibles con advertencia y espera exponencial (máx. 1 h) + circuit breaker.

## Componentes

| Módulo | Función |
|---|---|
| `collector.py` | Recolector en segundo plano, cursor de sincronización, backoff, lock de instancia única |
| `live_metrics.py` | Métricas del monitor solo desde SQLite; intervalo vs acumulado |
| `metadata_inspector.py` | Lectura de `$metadata`, campos reales, detección de funciones |
| `capability_probe.py` | Pruebas de compatibilidad `$top=1` |
| `odata_client.py` | Único punto de red: GET, límites, circuit breaker, autenticación `auto` |
| `database.py` | SQLite: registros, historial de lecturas, ciclos, caché, reportes |
| `pulse_service.py` | Reglas de negocio, consulta local, monitor |
| `analytics.py`, `report_generator.py` | Análisis histórico, CSV/XLSX/PDF |
| `app.py` | Servidor local (127.0.0.1), API JSON, arranque del recolector |
| `templates/`, `static/` | Monitor, Consulta histórica, Tendencias, Reportes, Estado de conexión |
| `tests/` | 148 pruebas (`unittest`) |

## Documentación

* [Instalación y comandos](docs/INSTALACION.md)
* [Manual de usuario](docs/MANUAL_USUARIO.md)
* [Arquitectura](docs/ARQUITECTURA.md)
* [Validaciones pendientes y requisitos que dependen del esquema](docs/VALIDACIONES_PENDIENTES.md)
* [Resultados de pruebas](docs/RESULTADOS_PRUEBAS.md)

## Estado honesto

* **No hubo conexión al servidor real**: desde el entorno de desarrollo `10.62.54.10:6065` no responde
  (se verificó que el recolector registra el timeout y aplica la espera sin reintentos inmediatos).
* Todo lo demás se probó con un servidor OData **simulado**; sus nombres de campos son ficticios y el
  código no los asume en modo real.
* Proyecto, WO y producto se muestran **solo si existen** en `ProductivityOverTime`. Si la cantidad es
  acumulada o por intervalo debe confirmarlo MES (la detección automática es una sugerencia).
