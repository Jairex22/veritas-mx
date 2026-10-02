# DEMO - Base de conocimiento: Defects, Symptoms, Repair y Reroute

> DOCUMENTO DEMO. Explicaciones conceptuales para demostración. No reemplaza el manual oficial.

## Diferencia entre Defect y Symptom

Palabras clave: defect, symptom, defecto, síntoma, diferencia

### Respuesta breve
Un Symptom (síntoma) describe lo que se observa en la prueba o inspección, por ejemplo "no enciende". Un Defect (defecto) describe la causa identificada, por ejemplo "componente U5 dañado". Primero se registra el síntoma y, después del diagnóstico en Repair/Debug, se documenta el defecto.

### Qué validar
- Que el síntoma registrado describa lo observado y no una suposición.
- Que el defecto se registre solo cuando el diagnóstico lo confirma.

### Cuándo escalar
Escala a Calidad si no existe un código de defecto adecuado en el catálogo.

## Por qué una unidad regresa a Repair

Palabras clave: regresa a repair, reparación, falla repetida, debug, retest

### Respuesta breve
Una unidad regresa a Repair cuando falla nuevamente una prueba (Fail), cuando se registra un nuevo síntoma o cuando el defecto anterior no quedó cerrado correctamente.

### Pasos
1. Revisa el historial de pruebas Pass/Fail de la unidad.
2. Revisa los defectos y síntomas registrados anteriormente.
3. Verifica si la reparación anterior fue documentada y cerrada.

### Qué validar
- Que la falla actual sea la misma o diferente a la anterior.

### Cuándo escalar
Escala a Ingeniería de Producto si la unidad regresa a Repair más de dos veces por el mismo síntoma.

## Cómo se documenta un reroute

Palabras clave: reroute, re-ruteo, cambio de ruta, documentar reroute

### Respuesta breve
Un reroute cambia la ruta de una unidad a otra operación del flujo. Solo personal autorizado lo realiza y debe documentarse el motivo, el serial, la operación origen y la operación destino.

### Pasos
1. Confirma con el supervisor que el reroute está autorizado.
2. Registra serial, Work Order, operación origen y operación destino.
3. Registra el motivo del reroute y quién lo autorizó.
4. Personal autorizado ejecuta el reroute en FactoryLogix.

### Cuándo detenerse
No ejecutes un reroute sin autorización: altera la trazabilidad de la unidad.

### Cuándo escalar
Escala a Soporte MES si el reroute requerido no está disponible en el process flow.

## Unproceed y Proceed

Palabras clave: unproceed, proceed, deshacer avance

### Respuesta breve
Proceed registra el avance de una unidad a la siguiente operación. Unproceed revierte un avance registrado por error. Unproceed es una acción controlada que debe realizar personal autorizado y documentarse.

### Cuándo escalar
Escala al supervisor antes de solicitar un Unproceed y documenta el motivo.
