# Manual de administración (Administrador de Producto)

La administración funcional de TimeFlow pertenece al **Departamento de Producto**. El rol *Administrador de Producto* puede consultar todas las solicitudes, pero **no puede aprobar** en nombre de jefas o jefes ni registrar en nombre del área administrativa.

## 1. Empleados (Administración → Empleados)

- **Buscar** por nombre, número, correo o área; incluir inactivos.
- **Nuevo empleado**:
  - Datos obligatorios: número de empleado y correo, ambos únicos; nombre y departamento.
  - Datos opcionales: área, puesto, fecha de ingreso (solo si está autorizada) y días de vacaciones iniciales. Si se dejan vacíos, se sugieren según la antigüedad.
  - **Jefa directa (filtro 1)** y **Jefe superior (filtro 2)**: deben ser personas distintas y distintas del empleado.
  - Roles: Jefa directa, Jefe superior, Administrador de Producto, Registro administrativo. Todos tienen además el rol Empleado.
- **Editar**:
  - Los cambios de jerarquía se aplican a las solicitudes **nuevas**; las que ya están en trámite conservan los aprobadores asignados al enviarlas. El historial de jerarquía se conserva en `ReportingHierarchy`.
  - Cambiar roles o desactivar una cuenta **cierra sus sesiones abiertas**.
  - No puede retirarse a sí mismo el rol de administrador.
- **Desbloquear**: cuentas bloqueadas por intentos fallidos (solo DEMO/TEST; en producción el acceso lo gestiona Entra ID).
- **Ajustar vacaciones** (ícono de palmera): días positivos o negativos con motivo obligatorio. Queda auditado. Coordine con RH antes de aplicarlo.

### Importación desde Excel
1. **Importar Excel → Descargar plantilla** (hojas *Empleados* e *Instrucciones*).
2. Una fila por empleado. Las columnas de jefa y jefe usan el correo, y esas personas pueden venir en el mismo archivo.
3. **Validar (simulación)**: informa fila por fila (duplicados en el archivo, correos inválidos o de otra persona, departamentos inexistentes). No guarda nada.
4. **Confirmar importación**: aplica todo en una sola transacción. Un número existente se actualiza. Máximo 1000 filas.

## 2. Organigrama
Vista jerárquica vigente (dirección → jefes superiores → jefas directas → equipo) con roles. Pulse un nombre para editarlo.

## 3. Configuración
- **Políticas**:
  - Tiempo extra: mínimo y máximo por solicitud, máximo mensual, días hacia atrás.
  - Calendario y vacaciones: días hábiles (1 = lunes … 7 = domingo), máximo de días consecutivos, anticipación, saldo negativo.
  - Avisos: recordatorio y urgencia (horas), buzón administrativo, firma obligatoria del solicitante.
  - Documentos: color corporativo, leyenda del PDF, retención.
  - Los cambios se auditan con los valores anteriores y nuevos. No representan reglas de nómina: valídelos con RH.
- **Días festivos**: cargados 2026–2027 (LFT art. 74). Agregue o desactive según el calendario oficial de cada año.
- **Tipos de permiso**: clasificaciones para permisos con y sin goce, con la opción «requiere documento». Una clasificación que requiere documento impide enviar la solicitud sin adjunto.
- **Correo y autenticación**: estado de las integraciones (solo lectura). Las credenciales se configuran fuera de la aplicación.

## 4. Correos (monitor de entrega)
Lista la cola con estado, intentos y último error, y permite **Ver** el HTML y **Reintentar** los fallidos.

| Estado | Significado |
|---|---|
| En cola / Enviando | Pendiente de procesar o en proceso |
| Enviado (Microsoft Graph) | Aceptado por Microsoft 365 |
| Registrado en buzón DEMO (no enviado) | Proveedor Mock; no salió a ningún buzón |
| Fallido | Agotó los reintentos (por defecto 6) |

## 5. Auditoría
Bitácora de todas las acciones relevantes:
- inicios de sesión, también fallidos;
- creación, envío, decisiones y firmas;
- invalidación de firmas;
- adjuntos;
- descargas de PDF y adjuntos;
- exportaciones;
- cambios de empleados, saldos y configuración.

**Verificar integridad** recorre la cadena de hash y avisa si algún registro fue alterado, insertado o eliminado fuera de la aplicación.

## 6. Reportes y Excel
Conjuntos disponibles: autorizadas, registradas/procesadas o historial completo, con filtros por periodo, tipo y empleado. El libro incluye Resumen, Detalle (tabla con filtros, fila superior fija, fechas con formato) y Metadatos. Cada exportación queda en la bitácora con su huella SHA-256. Los textos que podrían interpretarse como fórmulas se guardan como texto.

## 7. Salud del sistema
Estado de la base de datos, cola de correo, número de registros de auditoría, memoria, ambiente, modo de autenticación y proveedor de correo.

## 8. Operación diaria recomendada
- Revisar los correos **Fallidos** y las solicitudes **Urgentes**.
- Cada mes: verificar la integridad de la auditoría y revisar las exportaciones.
- Cada año: festivos, saldos del nuevo periodo (asignación) y parámetros con RH.
- Ante bajas de personal: desactivar la cuenta y reasignar su equipo editando la jerarquía.
