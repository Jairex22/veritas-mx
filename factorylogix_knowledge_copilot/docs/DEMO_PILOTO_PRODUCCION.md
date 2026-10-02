# DEMO, piloto y producción

## 1. Separación de entornos

| Aspecto | DEMO | PILOTO | PRODUCCIÓN |
|---|---|---|---|
| `app.environment` | DEMO | PILOT | PRODUCTION |
| Banner en pantalla | Amarillo “DEMO” | Amarillo “PILOT” | Sin banner |
| Documentos | `DEMO-*` ilustrativos | Reales aprobados de 1-2 líneas | Reales aprobados |
| Usuarios | `demo_*` automáticos | Nominales | Nominales (+ AD futuro) |
| Evaluación | `config/eval_set.yaml` DEMO | Preguntas reales de la línea piloto | Conjunto completo, periódico |
| Red | Local | Red interna, proxy HTTPS | Red interna, proxy HTTPS, respaldos programados |
| OData | Desactivado | Opcional, solo lectura | Opcional, solo lectura |

Los datos y usuarios DEMO solo se crean cuando el entorno es `DEMO`. Todo documento DEMO lleva `is_demo=1`,
código `DEMO-` y la leyenda “No es un procedimiento oficial”; su confianza nunca es “Alta”.

## 2. Pasos de DEMO → PILOTO

1. Respaldo.
2. Configuración → Parámetros → Entorno = `PILOT`.
3. Usuarios: desactivar `demo_*`; crear usuarios nominales; borrar `data\USUARIOS_DEMO.txt`.
4. Catálogo: desactivar documentos `DEMO-*`; luego eliminarlos (Gobierno → Retención, motivo “fin de demo”).
5. Cargar y aprobar documentos reales (`docs/GUIA_AGREGAR_CONOCIMIENTO.md`).
6. Reemplazar `config/eval_set.yaml` con preguntas reales y ejecutar Evaluaciones.
7. Completar `docs/CHECKLIST_SEGURIDAD.md`.

## 3. Datos reales que la empresa debe proporcionar

| # | Dato | Responsable sugerido |
|---|---|---|
| 1 | Procedimientos e instrucciones de trabajo vigentes y aprobados de FactoryLogix (Operations, Production, Analytics, NPI, xTend) | MES / Ingeniería de Manufactura |
| 2 | Manuales oficiales aprobados para uso interno (verificar licencia del fabricante) | MES |
| 3 | Propietario, aprobador, área, fechas efectiva/revisión/expiración y clasificación de cada documento | Data Steward / Calidad |
| 4 | Catálogo de clientes, productos, líneas, procesos, estaciones y módulos para filtros | Ingeniería / Producción |
| 5 | Ruta de escalamiento real (contactos, extensiones, horarios, niveles de urgencia) y áreas | Supervisores / MES |
| 6 | Glosario interno (abreviaturas, nombres de estaciones, sinónimos ES/EN) | MES / Producción |
| 7 | Códigos de defecto y síntomas, criterios de Repair/Debug y reroute autorizados | Calidad / Producto |
| 8 | Reglas de certificación de operadores por estación | Calidad / Capacitación |
| 9 | Plantillas de etiquetas y reglas de validación de packing/shipping | Shipping / Calidad |
| 10 | Matriz de roles y usuarios (nombre, rol, clasificación permitida) | TI / Gerencia |
| 11 | Políticas de retención y respaldo aprobadas | Legal / Calidad / TI |
| 12 | Preguntas reales frecuentes de piso con respuesta esperada y fuente (conjunto de evaluación) | Supervisores / MES |
| 13 | Opcional: URL OData, `$metadata`, cuenta de servicio de solo lectura y certificado | MES / TI |
| 14 | Opcional: servidor para LLM local y modelo aprobado; modelo de embeddings multilingüe aprobado | TI |
| 15 | Identidad visual: nombre, logo, colores, sitio, datos de soporte | Comunicación / MES |
| 16 | Servidor Windows destino, puerto, regla de firewall, certificado HTTPS interno | TI |
