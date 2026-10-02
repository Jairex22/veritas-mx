# DEMO - Instrucción de trabajo: Etiquetas, Packing y Shipping

> DOCUMENTO DEMO. No es una instrucción oficial.

## Qué revisar si una etiqueta no coincide

Palabras clave: etiqueta no coincide, label mismatch, código de barras, barcode

### Respuesta breve
Si la etiqueta no coincide con la unidad o con la orden, no la coloques ni la empaques. Compara serial, número de parte, revisión y Work Order contra el sistema.

### Pasos
1. Escanea el código de barras de la etiqueta.
2. Compara el serial impreso contra el serial registrado en FactoryLogix.
3. Compara número de parte y revisión contra la Work Order.
4. Separa la etiqueta incorrecta e identifícala.

### Qué validar
- Serial, número de parte, revisión, cantidad y Work Order.

### Resultado esperado
La etiqueta coincide exactamente con los datos de la unidad en el sistema.

### Cuándo detenerse
Detente si hay más de una etiqueta incorrecta seguida: puede ser un problema de plantilla.

### Cuándo escalar
Escala a Soporte MES y a Calidad si la plantilla de etiqueta imprime datos incorrectos.

## Packout y embarque

Palabras clave: packing, packout, empaque, shipping, embarque

### Respuesta breve
En packout se asocia cada unidad a su contenedor. Solo unidades que completaron todas las operaciones con resultado Pass deben empacarse.

### Pasos
1. Escanea la unidad en la estación de packout.
2. Escanea o asigna el contenedor.
3. Verifica la cantidad del contenedor antes de cerrarlo.

### Cuándo escalar
Escala a Shipping y Calidad si una unidad sin todas sus operaciones aparece en un contenedor.
