# Modelo de amenazas (STRIDE)

## 1. Alcance y activos

| Activo | Sensibilidad |
|---|---|
| Documentos y fragmentos (procedimientos, instrucciones) | Internal → Restricted |
| Preguntas y respuestas (`query_log`) | Interna; puede contener WO/seriales |
| Credenciales locales (hash) y secretos de conectores (.env) | Alta |
| Auditoría | Alta (evidencia) |
| Disponibilidad del asistente en piso | Media (existe ruta de escalamiento manual) |

Actores: operador legítimo, usuario curioso con rol bajo, insider con acceso al servidor, autor de documentos
(posible contenido malicioso), atacante en red interna, dependencia comprometida.

Fronteras de confianza: navegador ↔ servidor Streamlit; servidor ↔ archivos cargados; servidor ↔ LLM local;
servidor ↔ FactoryLogix OData; servidor ↔ sistema de archivos/SO.

## 2. Amenazas y controles

| # | STRIDE | Amenaza | Controles implementados | Prueba |
|---|---|---|---|---|
| T1 | S | Suplantación / fuerza bruta | scrypt con sal; bloqueo tras 5 fallos (15 min); rate limit de login; mensajes genéricos y hash ficticio (anti-enumeración); sesión por inactividad; cambio obligatorio de contraseña inicial | `test_auth_users_audit.py` |
| T2 | E | Acceso a fuentes de mayor clasificación | Filtro de clasificación en SQL antes del ranking; descargas validan clearance; auditoría de intentos (`rag.restricted_source_denied`) | `test_chat_service.py`, `test_security_controls.py` |
| T3 | E | Uso de contenido no aprobado/vencido | Elegibilidad: Approved + publicado + vigente + activo; expiración automática; pruebas previas a publicar | `test_knowledge_workflow.py` |
| T4 | T | Prompt injection en documentos | Detección en ingesta y por fragmento; confirmación explícita del aprobador; oraciones sospechosas excluidas de respuestas y del contexto del LLM; relevancia recalculada sin ellas | `test_security_controls.py`, eval E21/E25 |
| T5 | T | Prompt injection en preguntas | Pregunta tratada como dato; aviso; auditoría; el LLM recibe fuentes y pregunta en etiquetas de datos; verificación de fidelidad | `test_chat_service.py` |
| T6 | T | Archivos maliciosos (extensión falsa, ejecutables, zip bomb, macros) | Allowlist, firma (magic bytes), límite de tamaño/páginas/filas, ratio de compresión, rechazo de vbaProject, timeout de extracción | `test_security_controls.py` |
| T7 | T | Path traversal | `safe_filename` + `safe_join` (resolución dentro del directorio base) | `test_security_controls.py` |
| T8 | T | XSS | Contenido escapado (HTML/Markdown); `unsafe_allow_html` solo con CSS estático y colores validados por regex; reportes HTML escapados | `test_security_controls.py`, `test_llm_and_export.py` |
| T9 | T | SQL injection | SQL parametrizado; columnas dinámicas en allowlist; términos FTS saneados y citados | `test_security_controls.py` |
| T10 | T | CSV/Excel injection | Prefijo `'` para `= + - @ \t \r` | `test_llm_and_export.py` |
| T11 | R | Repudio de acciones | Auditoría append-only (triggers) + cadena SHA-256 verificable; correlation ID | `test_auth_users_audit.py` |
| T12 | I | Filtración de secretos / datos en logs | Secretos solo en entorno; redacción en logs; preguntas y documentos no se escriben en el log técnico; errores sin trazas ni rutas | `test_security_controls.py` |
| T13 | I | Exfiltración a Internet | Sin APIs de nube; telemetría Streamlit off; LLM solo loopback/privado; OData con allowlist de host; `trust_env=False` | `test_codebase_policy.py`, `test_llm_and_export.py` |
| T14 | D | Abuso / saturación | Rate limit de chat; límites de tamaño; timeouts; circuit breaker OData | `test_connectors.py` |
| T15 | E | Acciones de producción automáticas | No existe código de escritura en FactoryLogix; conector solo GET; detección de solicitudes de transacción | `test_connectors.py`, `test_chat_service.py` |
| T16 | T | Aprendizaje no supervisado de conversaciones | Correcciones en bandeja; Q&A requiere aprobación de otra persona | `test_incidents_feedback_eval.py` |
| T17 | I | Uso indebido del sentimiento | Solo etiqueta con expiración; desactivable; sin rankings ni datos por empleado en analítica | `test_chat_service.py`, `test_incidents_feedback_eval.py` |
| T18 | S/T | CSRF en formularios | `enableXsrfProtection = true`, CORS restringido | Configuración |

## 3. Riesgos residuales y mitigaciones recomendadas

| Riesgo | Recomendación |
|---|---|
| Tráfico HTTP sin cifrar en la red interna | Proxy inverso con HTTPS (IIS/NGINX) y certificado interno; cabeceras `Content-Security-Policy`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Strict-Transport-Security` |
| Insider con acceso de escritura a `data/` | Permisos NTFS restringidos a la cuenta de servicio; respaldos fuera del equipo; exportar auditoría a SIEM |
| Rate limiting en memoria (se reinicia al reiniciar) | Suficiente para piloto; en producción complementar con proxy |
| Hilo de extracción que excede el timeout sigue en segundo plano | Límites de páginas/filas reducen el riesgo; para archivos no confiables usar un equipo de ingesta separado |
| Heurística de contradicciones/injection no exhaustiva | Revisión humana obligatoria antes de publicar; evaluación RAG periódica |
| Dependencias de terceros | Inventario de licencias; `wheelhouse` revisado; escaneo de vulnerabilidades corporativo |
