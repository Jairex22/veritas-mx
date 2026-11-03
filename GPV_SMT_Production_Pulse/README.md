# GPV SMT Production Pulse — v1.0.0

**GPV Americas | SMT Production Pulse** — Monitoreo inteligente de productividad de SMT.

Aplicación web local, de solo lectura, que consulta la entidad **`ProductivityOverTime`** de
FactoryLogix vía OData bajo demanda, guarda los resultados en una caché SQLite local y muestra
métricas, gráficas y reportes **calculados únicamente con campos confirmados**.

> Prioridades de diseño: 1) no saturar el servidor OData, 2) facilidad de uso para operadores,
> 3) precisión y trazabilidad de los datos.

## Inicio rápido (Windows 11, cuenta estándar)

```bat
cd GPV_SMT_Production_Pulse
py app.py --demo
```

Abrir **http://127.0.0.1:8765** en el navegador. Sin dependencias que instalar.

Para el servidor real (después de leer [docs/INSTALACION.md](docs/INSTALACION.md)):

```bat
py app.py --live
```

## Qué incluye

| Componente | Archivo |
|---|---|
| Servidor web local (biblioteca estándar, 127.0.0.1) | `app.py` |
| Inspector de `$metadata` (también ejecutable por línea de comandos) | `metadata_inspector.py` |
| Cliente OData protegido (single-flight, límites, circuit breaker) | `odata_client.py` |
| Pruebas de compatibilidad de filtros (`$top=1`) | `capability_probe.py` |
| Lógica de negocio / orquestación | `pulse_service.py` |
| Base SQLite (caché, historial, reportes, ajustes) | `database.py` |
| Análisis de productividad | `analytics.py` |
| Reportes CSV / XLSX nativo / vista PDF | `report_generator.py` |
| Validación y seguridad | `security.py` |
| Configuración centralizada | `settings.py`, `config.json` |
| Simulador del modo DEMO | `demo_source.py` |
| Interfaz (HTML/CSS/JS nativo, gráficas SVG) | `templates/`, `static/` |
| 114 pruebas automatizadas (`unittest`) | `tests/` |

## Documentación

* [Manual de instalación](docs/INSTALACION.md)
* [Manual de usuario](docs/MANUAL_USUARIO.md)
* [Arquitectura](docs/ARQUITECTURA.md)
* [Validaciones pendientes contra FactoryLogix real](docs/VALIDACIONES_PENDIENTES.md)
* [Resultados de pruebas](docs/RESULTADOS_PRUEBAS.md)

## Ejecutar las pruebas

```bat
py -m unittest discover -s tests -v
```

## Estado honesto de la validación

* Todo el software fue probado contra un **simulador local** y archivos de ejemplo **simulados**.
* **No se ha realizado ninguna conexión al servidor `http://10.62.54.10:6065/odata/`**: no era
  accesible desde el entorno de desarrollo. Los nombres de campos del modo DEMO son ficticios.
* La compatibilidad real debe confirmarse en una computadora autorizada de GPV siguiendo
  [docs/VALIDACIONES_PENDIENTES.md](docs/VALIDACIONES_PENDIENTES.md).
