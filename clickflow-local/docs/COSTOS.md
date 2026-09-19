# Desglose de servicios y costos estimados

Estos son **estimados de referencia con supuestos explícitos**, no cifras
garantizadas: cámbialos según el proveedor y volumen reales que elijas.
Ningún número aquí es una promesa de ingresos ni de ahorro; son costos de
operar la infraestructura.

## 1. Hosting

| Servicio | Supuesto | Estimado mensual (MXN aprox.) |
|---|---|---|
| Backend (Node + SQLite) | 1 instancia pequeña (0.5-1 vCPU, 512MB-1GB RAM) en un PaaS (Render, Railway, Fly.io) o VPS económico | $100–$300 |
| Frontend estático | Build de Vite servido por el mismo backend o un CDN gratuito/económico (Netlify, Cloudflare Pages) | $0–$100 |
| Dominio propio | Opcional; puede usarse un subdominio gratuito del proveedor mientras se prueba | $200–$400 **por año** |
| Certificado HTTPS | Incluido gratis en la mayoría de los PaaS/CDN modernos (Let's Encrypt) | $0 |
| Respaldo de la base de datos | Copia periódica del archivo SQLite (puede automatizarse con un cron simple) | $0–$50 (si usas almacenamiento externo) |

**Supuesto clave:** un solo negocio pequeño con tráfico moderado (decenas
de conversaciones al día) no necesita más que el plan más económico de
cualquier PaaS. Esta arquitectura soporta varios negocios en la misma
instancia (como la demo), lo que reparte este costo entre más de un
negocio si se opera como plataforma compartida.

## 2. Inteligencia artificial (OpenAI)

El costo depende del modelo elegido (`OPENAI_MODEL`), del largo del
historial de conversación (acotado a los últimos mensajes) y del número de
llamadas a herramientas por turno (limitado a un máximo de pasos). No
incluimos aquí un precio por token porque cambia con el tiempo y por
modelo: **antes de operar, confirma el precio vigente en la página oficial
de precios de OpenAI** para el modelo que configures.

Método para estimar tu costo mensual:

```
costo ≈ conversaciones/mes
        × mensajes por conversación
        × (tokens de entrada × precio_entrada + tokens de salida × precio_salida)
```

Con un modelo pequeño/económico y conversaciones cortas (que es el caso de
uso típico de un negocio local: preguntas de precio, una cita, un pedido),
el consumo de tokens por conversación suele ser bajo. El panel de
administración (**Consumo de IA**) te muestra el conteo real de llamadas y
tokens usados, para que ajustes el estimado con datos propios en vez de
una proyección genérica.

**Si no configuras una API key**, este costo es $0 — la app sigue
funcionando con el motor de respaldo determinista para catálogo,
cotizaciones, citas y contacto.

## 3. WhatsApp (futuro, no incluido en esta versión)

La versión actual solo abre un enlace `wa.me` con un mensaje preparado
(costo $0, no requiere cuenta de WhatsApp Business API). Automatizar
completamente WhatsApp (recibir y responder sin que la persona abra la
app) requeriría:

- Una cuenta de WhatsApp Business API a través de un proveedor autorizado
  por Meta (o directamente con Meta Cloud API).
- Verificación de negocio ante Meta.
- Costo por conversación, que varía por país y categoría de plantilla
  (servicio, marketing, utilidad) — **cotizar directamente con Meta o el
  proveedor elegido al momento de integrar**, ya que cambia con frecuencia
  y por región.

## 4. Mantenimiento y soporte

| Actividad | Supuesto |
|---|---|
| Actualizaciones de dependencias y monitoreo básico | Algunas horas al mes; costo variable según quién lo haga (interno o freelance) |
| Ajustes de catálogo/políticas por el propio dueño | $0 — está diseñado para que el dueño lo haga solo desde el panel |
| Soporte técnico ante incidentes | Variable; depende del proveedor de hosting y de si hay un desarrollador de respaldo |

## 5. Resumen de supuestos

- Un solo negocio pequeño, tráfico bajo-moderado, sin necesidad de alta
  disponibilidad (99.9%+) todavía.
- Precios de hosting en pesos mexicanos, con base en rangos públicos
  típicos de proveedores como Render/Railway/Fly.io/VPS económicos al
  momento de escribir esto; **verifica precios vigentes** antes de decidir.
- No se incluyen costos de desarrollo/personalización adicional más allá
  de lo entregado en este repositorio.
