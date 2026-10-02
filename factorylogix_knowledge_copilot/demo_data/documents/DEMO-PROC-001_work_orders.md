# DEMO - Procedimiento: Consulta de Work Orders y avance de unidades

> DOCUMENTO DEMO. Contenido ilustrativo generado para demostración. NO es un procedimiento oficial de FactoryLogix ni de la empresa. Debe sustituirse por el procedimiento aprobado.

## Revisar el estado de una Work Order

Palabras clave: work order, orden de trabajo, estado, status, WO

### Respuesta breve
El estado de una Work Order (orden de trabajo) se consulta en FactoryLogix desde la vista de órdenes de trabajo, buscando por el número de WO.

### Pasos
1. Abre FactoryLogix con tu usuario autorizado.
2. Entra al módulo de producción y abre la lista de Work Orders.
3. Busca la orden por su número de Work Order.
4. Revisa el campo de estado (status) de la orden: por ejemplo Released, In Process o Closed.
5. Revisa la cantidad planeada contra la cantidad completada.

### Qué validar
- Que el número de Work Order coincida con la hoja de ruta física.
- Que la orden esté liberada (Released) antes de iniciar producción.

### Resultado esperado
La orden muestra un estado coherente con lo que ocurre en piso y las cantidades cuadran.

### Cuándo detenerse
Detente si la orden aparece cerrada o en espera (On Hold) y aun así hay material en la línea.

### Cuándo escalar
Escala al supervisor y a Soporte MES si el estado no coincide con la realidad del piso o si no encuentras la orden.

## Por qué una unidad no puede avanzar

Palabras clave: unidad no avanza, no puede avanzar, bloqueada, cannot advance, proceed rechazado

### Respuesta breve
Una unidad normalmente no puede avanzar cuando no está en la operación correcta del flujo de proceso, tiene un defecto abierto, el operador no está certificado o falta un componente requerido.

### Pasos
1. Escanea el número de serie y revisa la operación actual de la unidad.
2. Compara la operación actual con la estación donde te encuentras.
3. Revisa si la unidad tiene defectos abiertos pendientes de Repair.
4. Verifica que tu certificación de operador esté vigente para la estación.
5. Revisa el mensaje de validación que muestra FactoryLogix y anótalo completo.

### Qué validar
- Que el serial escaneado sea el correcto.
- Que la unidad no tenga un defecto abierto.
- Que la estación corresponda a la siguiente operación del process flow.

### Resultado esperado
Identificas la causa del bloqueo con base en el mensaje de validación y la operación actual.

### Cuándo detenerse
Detente y no intentes forzar el avance si el sistema muestra una excepción de validación que no entiendes.

### Cuándo escalar
Escala a Soporte MES con el serial, la Work Order, la estación y el mensaje de error exacto.

## Cómo saber cuál es la siguiente operación

Palabras clave: siguiente operación, next operation, process flow, ruta

### Respuesta breve
La siguiente operación se determina por el process flow (flujo de proceso) asignado a la Work Order y se consulta en el historial de la unidad.

### Pasos
1. Escanea el serial de la unidad.
2. Consulta el historial o route de la unidad.
3. Identifica la operación completada más reciente.
4. Revisa en el process flow cuál operación sigue después de ella.

### Qué validar
- Que la unidad no tenga un reroute aplicado que cambie la ruta normal.

### Resultado esperado
Conoces la siguiente operación y la estación donde debe procesarse la unidad.

### Cuándo escalar
Escala a Ingeniería de Manufactura si el process flow no coincide con la instrucción de trabajo.

## Qué significa In Process

Palabras clave: in process, en proceso, estado de unidad

### Respuesta breve
In Process (en proceso) indica que la unidad ya inició su ruta de producción y aún no ha completado todas las operaciones del process flow.

### Qué validar
- Que la unidad tenga registros de operaciones recientes.
- Que no lleve demasiado tiempo detenida en la misma operación (posible WIP estancado).

### Cuándo escalar
Escala al supervisor si una unidad permanece In Process sin movimiento durante más tiempo del esperado en tu línea.
