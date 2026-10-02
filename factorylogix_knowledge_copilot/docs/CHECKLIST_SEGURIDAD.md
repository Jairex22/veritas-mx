# Checklist de seguridad

Marcar antes de pasar de DEMO a PILOTO y de PILOTO a PRODUCCIÓN.

## Identidad y acceso
- [ ] Contraseña de `admin` inicial cambiada y `data\PRIMER_ACCESO_ADMIN.txt` inexistente.
- [ ] Cuentas nominales creadas; `admin` genérico desactivado o resguardado.
- [ ] Usuarios `demo_*` desactivados y `data\USUARIOS_DEMO.txt` eliminado.
- [ ] Roles asignados por mínimo privilegio (revisar `docs/MATRIZ_RBAC.md`).
- [ ] `governance.require_four_eyes = true`.
- [ ] Expiración de sesión acorde a la política (por defecto 30 min).

## Datos y gobierno
- [ ] Entorno configurado como `PILOT` o `PRODUCTION`.
- [ ] Documentos `DEMO-*` desactivados/eliminados; solo fuentes aprobadas por propietarios reales.
- [ ] Matriz de acceso por clasificación validada por Calidad/TI.
- [ ] Políticas de retención validadas por Legal/Calidad.
- [ ] `config/eval_set.yaml` reemplazado con preguntas reales y evaluación ≥ objetivo acordado.

## Plataforma
- [ ] Carpeta de la aplicación con permisos NTFS solo para la cuenta que la ejecuta y administradores de TI.
- [ ] `.env` presente solo en el servidor, con permisos restringidos; nunca en el ZIP ni en repositorios.
- [ ] Proxy inverso HTTPS con cabeceras de seguridad (CSP, X-Frame-Options, nosniff, Referrer-Policy, HSTS).
- [ ] Firewall: puerto expuesto solo a la VLAN de producción/oficinas.
- [ ] Telemetría de Streamlit desactivada (`.streamlit/config.toml`).
- [ ] Respaldos programados y prueba de restauración documentada.

## Integraciones
- [ ] OData con cuenta de servicio **solo lectura**, host en `allowed_hosts`, TLS verificado.
- [ ] LLM local (si se usa) en loopback o red privada; modelo con licencia aprobada.
- [ ] Correo deshabilitado o con SMTP interno y dominios permitidos.

## Verificación
- [ ] `pytest` completo en verde en el servidor destino.
- [ ] Salud del sistema sin estados FAIL; cadena de auditoría íntegra.
- [ ] Revisión de `logs\app.log`: sin secretos ni contenido confidencial.
