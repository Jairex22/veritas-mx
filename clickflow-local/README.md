# ClickFlow Local

Asistente virtual configurable para negocios locales. Resuelve dudas, ayuda a
elegir productos/servicios y facilita solicitudes de pedidos, cotizaciones y
citas — sin prometer aumentos de ventas: es una herramienta para probar con
clientes reales y medir con datos verificables (conversaciones, solicitudes,
contactos), no una máquina de "ventas garantizadas".

Este repositorio contiene una aplicación **funcional y completa**: backend
real, base de datos persistente, integración de IA con function calling,
widget embebible, página del asistente compartible por enlace, y panel de
administración. Incluye una demo con 3 negocios ficticios (barbería, pastelería
y carnicería), claramente marcados como datos de demostración.

---

## 1. Arquitectura (resumen y por qué)

```
clickflow-local/
├─ server/     Backend: Node.js + Express + TypeScript + SQLite
└─ web/        Frontend: React + TypeScript + Vite (SPA)
```

**Backend — Node/Express/TypeScript + SQLite (better-sqlite3).**
Se eligió SQLite porque el alcance inicial explícitamente permite "una
instalación independiente por negocio", y SQLite da una base de datos
**real y persistente** (un archivo `.sqlite3`) sin necesitar levantar ni
administrar un servidor de base de datos aparte — mínima infraestructura
para lo que pide esta primera versión. El mismo esquema (ver
`server/src/db/db.ts`) es SQL estándar y migrable a Postgres si el producto
necesita más concurrencia o escalar a muchos negocios en un solo despliegue
compartido. `better-sqlite3` es además **síncrono**, lo que en Node (de un
solo hilo) hace que el patrón "verificar-y-crear" de las solicitudes
(idempotencia) sea atómico sin necesidad de locks adicionales.

**Multi-negocio con aislamiento en el servidor.** Aunque la primera versión
puede instalarse una vez por negocio, esta implementación de referencia ya
corre varios negocios sobre una sola instancia para simplificar la demo.
El aislamiento NO depende de ocultar botones en el cliente: cada ruta
pública resuelve el negocio por el `slug` de la URL en el servidor
(`middleware/tenant.ts`), y cada ruta de administración obtiene el
`businessId` **del token firmado**, nunca de un parámetro que mande el
cliente (`middleware/auth.ts`). El modelo de IA tampoco elige a qué negocio
accede: recibe únicamente los datos del negocio ya resuelto por el servidor.

**IA — OpenAI Responses API con function calling, modelo configurable.**
El motor de conversación (`server/src/ai/agent.ts`) usa la Responses API
oficial de OpenAI con herramientas (`tools`) tipadas y `parameters` en JSON
Schema. El modelo **propone** llamadas a herramientas; el servidor
(`server/src/ai/tools.ts`) es quien realmente consulta la base de datos,
calcula cotizaciones y arma propuestas — nunca al revés. El modelo nunca
persiste nada directamente: crear una solicitud real siempre pasa por un
endpoint aparte que exige una confirmación explícita de la persona
(ver sección 4). El modelo (`OPENAI_MODEL`) y el límite de pasos del agente
son configurables por variable de entorno, con un tope duro de pasos por
turno para controlar costo y evitar bucles.

**Si falta la credencial de OpenAI, la app sigue funcionando de verdad.**
Catálogo, cotizaciones, citas y contacto **no dependen de la IA**: son
endpoints REST deterministas que cualquier negocio puede usar aunque nunca
configure una API key. Solo la conversación libre en lenguaje natural usa
un motor de respaldo determinista y transparente
(`server/src/ai/fallbackEngine.ts`) que dice explícitamente "IA pendiente de
configurar" en vez de simular una conversación inteligente que no existe.
Esta separación (acciones reales vía REST + conversación vía IA opcional)
es la decisión de arquitectura más importante del proyecto: reduce el
riesgo de que un negocio quede "bloqueado" sin credencial, y hace que la
integración de IA sea un mejor conversacional, no un requisito para operar.

**Frontend — React + TypeScript + Vite, sin backend-for-frontend aparte.**
Una sola SPA sirve tres superficies:
- **Página del asistente** (`/assistant/:slug`), compartible por enlace.
- **Widget embebible**: un `<script>` (`server/public/embed/embed.js`) que
  inyecta un botón flotante y un `<iframe>` apuntando a esa misma página del
  asistente con `?embed=1`. Usar un iframe (en vez de inyectar React
  directamente en la página anfitriona) fue deliberado: aísla estilos y
  JavaScript del sitio que lo aloja (sin colisiones de CSS), y evita que el
  sitio anfitrión pueda leer las conversaciones del widget.
- **Panel del dueño** (`/admin/...`), protegido con JWT.

**Autenticación del panel:** JWT firmado por el servidor (`JWT_SECRET`),
enviado como `Authorization: Bearer`. Sin cuentas para las personas
visitantes: solo un identificador de sesión de navegador
(`localStorage`) para mantener el hilo de la conversación, sin pedir datos
personales para ver precios o catálogo.

---

## 2. Requisitos

- Node.js 20+ y npm.
- (Opcional) una API key de OpenAI para la conversación libre con IA.

## 3. Instalación y arranque (desarrollo)

```bash
# 1) Backend
cd clickflow-local/server
npm install
cp .env.example .env
# Genera un JWT_SECRET propio y ponlo en .env:
node -e "console.log(require('crypto').randomBytes(48).toString('hex'))"
# (Opcional) agrega tu OPENAI_API_KEY en .env para IA conversacional real.
npm run seed     # crea los 3 negocios de demostración
npm run dev      # http://localhost:8787

# 2) Frontend (en otra terminal)
cd clickflow-local/web
npm install
npm run dev      # http://localhost:5173 (usa proxy /api -> :8787 en desarrollo)
```

Abre `http://localhost:5173/assistant/barberia-don-cesar` para probar el
asistente, o `http://localhost:5173/admin/login` para el panel (credenciales
de demo abajo).

## 4. Publicación (producción)

1. **Backend**: `npm run build && npm start` en `server/`, detrás de HTTPS
   (por ejemplo, con un proxy como Caddy/Nginx o un PaaS). Define en el
   entorno: `JWT_SECRET`, `OPENAI_API_KEY` (opcional), `OPENAI_MODEL`,
   `CORS_ORIGIN` (dominio del frontend), y `DATA_DIR` apuntando a un disco
   persistente (no efímero) para el archivo SQLite.
2. **Frontend**: `npm run build` en `web/` genera `web/dist/` — archivos
   estáticos que puedes servir desde cualquier CDN/hosting estático,
   configurando `VITE_API_BASE_URL` hacia la URL pública del backend antes
   de compilar.
3. **Widget**: en la página del negocio, agregar:
   ```html
   <script
     src="https://TU-DOMINIO-BACKEND/embed/embed.js"
     data-business="barberia-don-cesar"
     data-base-url="https://TU-DOMINIO-FRONTEND"
     defer
   ></script>
   ```
   Esto se probó sirviendo el script desde un origen y cargándolo en una
   página HTML distinta (ver `docs/QA_CHECKLIST.md`, recorrido "Usar el
   widget en otra página").

## 5. Estructura de carpetas relevante

```
server/src/
  db/            esquema SQLite + acceso a datos
  services/      catálogo, cotización, horarios, solicitudes (lógica de negocio pura)
  ai/            system prompt, definición de herramientas, agente, respaldo determinista
  middleware/    auth admin, límite de tasa, resolución de negocio (tenant)
  routes/        endpoints públicos y de administración
web/src/
  pages/         AssistantPage (chat) + páginas del panel (/admin/*)
  components/chat/  UI del chat: catálogo, flujos de pedido/cita/contacto, propuestas de IA
  lib/           cliente de API, sesión de navegador, tema visual
```

## 6. Configuración de ejemplo (sin secretos)

`server/.env.example` documenta cada variable. Nunca commitees tu `.env`
real. Los tres negocios de demostración (`barberia-don-cesar`,
`pasteleria-dulce-trigo`, `carniceria-la-res-buena`) se crean con
`npm run seed` y quedan marcados `isDemo: true` en la base de datos.

Credenciales de panel de demo:

| Negocio | Slug | Correo | Contraseña |
|---|---|---|---|
| Barbería Don César (demo principal) | `barberia-don-cesar` | admin@barberiadoncesar.mx | demo1234 |
| Pastelería Dulce Trigo (ejemplo) | `pasteleria-dulce-trigo` | admin@dulcetrigo.mx | demo1234 |
| Carnicería La Res Buena (ejemplo) | `carniceria-la-res-buena` | admin@larestbuena.mx | demo1234 |

Cambia estas contraseñas antes de usar esto con datos reales.

## 7. Documentos relacionados

- [`docs/MANUAL_DUENO.md`](docs/MANUAL_DUENO.md) — manual breve para el dueño del negocio.
- [`docs/QA_CHECKLIST.md`](docs/QA_CHECKLIST.md) — recorridos de verificación: ejecutados, simulados y pendientes.
- [`docs/COSTOS.md`](docs/COSTOS.md) — desglose de servicios necesarios y costos estimados, con supuestos explícitos.
- [`docs/FUNCIONES.md`](docs/FUNCIONES.md) — lista honesta de qué funciona hoy y qué queda pendiente.

## 8. Límites conocidos de esta primera versión (ver también `docs/FUNCIONES.md`)

- No hay agenda/calendario real conectado: las citas quedan como
  "pendiente de confirmación", nunca se auto-confirman.
- No se procesan pagos ni se piden datos bancarios.
- WhatsApp se abre con un mensaje preparado (`wa.me`) que la persona debe
  enviar ella misma; la automatización completa vía la API oficial de
  Meta queda para una integración posterior (requiere cuenta de WhatsApp
  Business API, verificación de Meta y tiene costo por conversación).
- La conversación libre con IA requiere una API key de OpenAI; sin ella,
  el resto de la aplicación (catálogo, cotizaciones, citas, contacto)
  sigue funcionando con un motor de respaldo determinista, transparente
  sobre su propia limitación.
