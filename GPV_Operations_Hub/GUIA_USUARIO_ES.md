# Guía de usuario

Entre a la URL del portal con su usuario. Lo que ve depende de su **rol** (Administrador,
Jefe/Supervisor, Ingeniero/Analista, Operador/Lector) y de sus **áreas**. Si un botón indica
«No tiene permiso», el servidor bloqueó la operación: solicite el permiso a un administrador.

La barra superior muestra «Actualizado hh:mm:ss» (última consulta al servidor) y la campana de
notificaciones. Los datos cambian cuando alguien importa un archivo o captura avance: **no** es tiempo real.

## 1. Comunicados

* **Leer**: Comunicados › abra el aviso. Si dice «Confirmar lectura», pulse el botón.
* **Publicar** (jefes): «Nuevo comunicado» › título, mensaje, prioridad, vigencia, destinatarios
  (áreas, turnos, grupos, roles; vacío = todos), adjuntos, «requiere confirmación». Al publicar se
  crean notificaciones internas (no se envía correo). En el detalle verá quién leyó y confirmó.
* **Comentar / dudas / incidencias**: al pie de comunicados, órdenes y mejoras Kaizen. Las
  incidencias pueden marcarse como resueltas por quien tenga permiso.
* **Conversaciones**: Comunicados › Conversaciones › elija participantes.

## 2. Producción (plan)

1. Producción › elija periodo (hoy, semana, mes, rango) y filtros. Los filtros se recuerdan.
2. La tabla muestra meta, buenas, pendiente, avance, vencimiento, estado, prioridad, fuente y antigüedad.
   «No calculable» indica meta cero o desconocida; las órdenes atrasadas se marcan en rojo.
3. Abra una orden para ver historial, registros que la sustentan, proyección (estimación) y comentarios.
4. **Modificar meta/prioridad** (jefes): formulario de la orden, con **motivo obligatorio**; queda en el historial.
5. **Capturar avance** (operador asignado): fecha, turno, buenas, rechazo, scrap. Queda auditado.
6. «Exportar Excel/CSV» exporta exactamente la selección actual.

## 3. Cargar información (Excel/CSV)

1. Cargar información › elija el **dataset** destino › arrastre el archivo › «Cargar Excel» o «Cargar CSV».
2. **Vista previa y mapeo**: verifique hoja, fila de encabezados, codificación y separador (se
   detectan; puede cambiarlos). Asigne columnas a campos (las conocidas se sugieren). Elija orden de
   fecha y separador decimal si son ambiguos (el sistema no adivina). Elija modo:
   * *Anexar*: agrega nuevas claves y omite las existentes.
   * *Actualizar por clave*: inserta nuevas y actualiza las que cambiaron.
   * *Reemplazar alcance*: además retira registros vigentes del alcance (fechas/línea) que no vienen en el archivo.
   * Datasets *snapshot* (acumulados) siempre reemplazan la captura vigente: nunca suman.
   Puede guardar el mapeo como perfil para la próxima vez.
3. **Validar**: muestra leídas, aceptadas, rechazadas, nuevas, actualizadas, reemplazadas, sin
   cambios, omitidas y retiradas; errores por hoja/fila/columna con explicación; «Descargar errores (CSV)».
   No se modifica la base.
4. **Importar**: aplica los cambios; si hay errores, active «Importar solo filas válidas» o corrija el archivo.
5. **Historial**: cada lote conserva el archivo original y su resumen. «Revertir» (jefes) deshace el
   lote sin borrar cambios posteriores (los conflictos se listan).

Consejos: guarde seriales y órdenes como texto en Excel; los valores con 16+ dígitos guardados como
número ya perdieron dígitos y se rechazan. Las fórmulas sin valor guardado se calculan si son del
subconjunto soportado; si no, se rechazan (abra y guarde el archivo en Excel).

## 4. Dashboard

* KPIs con definición al pasar el mouse. Clic en una barra de línea o turno filtra todas las vistas
  (las «fichas» arriba muestran el filtro; × para quitarlo). Clic en un punto diario filtra ese día.
* «Ver registros» abre el detalle que sustenta los indicadores con los mismos filtros.
* «Mis dashboards»: cree, duplique, configure widgets (dimensión, medida, agregación, gráfico,
  orden, límite, ancho), campos calculados (`qty_scrap / (qty_good + qty_scrap) * 100`) y unión con la
  meta del plan (se valida que no multiplique cantidades). Comparta con roles, áreas o todos.

## 5. Reportes

1. Reportes › plantilla (diario, semanal, atrasos, calidad, por línea, Kaizen), periodo y filtros, formatos.
2. «Generar reporte»: se toma una instantánea; todos los formatos muestran los mismos totales.
3. Historial: descargue versiones anteriores. Si falló, «Reintentar».
4. «Programar reporte» (jefes): diario/semanal/por turno, hora local, destinatarios internos. Requiere
   el proceso `run_scheduler` en el servidor; muestra la próxima generación y el último resultado.

## 6. Hoja de cálculo

* Crear libro, abrir XLSX/CSV (se listan las características que no se importan) o editar un dataset.
* Teclado: flechas, Enter/F2 editar, Supr borrar, Ctrl+C/X/V, Ctrl+Z/Y, Ctrl+S guardar, Shift+flechas seleccionar.
* Barra: insertar/eliminar/duplicar filas y columnas (las fórmulas se ajustan), ordenar, filtrar,
  buscar/reemplazar, formatos (texto, número, fecha, porcentaje, decimales, negrita), formato
  condicional, validación, proteger columna (propietario), agrupar filas (▸/▾), congelar
  encabezados (congela filas/columnas arriba e izquierda del cursor), tabla dinámica, exportar.
* Pestañas: doble clic para renombrar (actualiza fórmulas), +, duplicar, mover, eliminar (avisa referencias rotas).
* Los resultados de fórmulas los calcula el servidor. Funciones y reglas: ver «Funciones soportadas».
* **Conflictos**: si alguien guardó antes, verá un aviso y podrá guardar su trabajo como copia o recargar.
* **Publicar al dataset** (jefes): envía la hoja guardada al asistente de importación para validar e importar con trazabilidad.

## 7. Documentos

1. Cargue archivos (carpeta, etiquetas y permiso: solo yo, mi área, todos).
2. Abra un documento para ver sus herramientas. Cada operación crea un archivo **nuevo**; el original no cambia.
   * PDF: organizar páginas con miniaturas (arrastrar, duplicar, eliminar, rotar), cortar por grupos
     (`1,3;2,4-5`), cada N páginas o una por archivo, extraer/eliminar, recortar márgenes (visual, no
     censura), numerar, marca de agua, texto, a imágenes, texto (TXT), tablas a Excel/CSV, optimizar
     (muestra tamaño antes/después), OCR (si está instalado). PDF protegidos: ingrese la contraseña (no se guarda).
   * PowerPoint: lista de diapositivas con advertencias de preservación, organizar/extraer/duplicar,
     exportar a PDF (con LibreOffice).
   * Excel: extraer/ordenar/duplicar/renombrar hojas, dividir por hoja, rangos, cantidad o valor de
     columna, PDF de un rango, CSV.
   * CSV: dividir conservando encabezado, quitar duplicados con vista previa, limpiar espacios,
     convertir tipos, cambiar separador y codificación, a Excel.
   * Word: secciones por título, organizar bloques, reemplazar texto conservando formato, generar
     desde plantilla `{{campo}}`, cortar por páginas (resultado PDF, con LibreOffice).
3. Lote: marque varios en la lista › combinar PDF, combinar documentos distintos en un PDF, imágenes a PDF,
   combinar PPTX/DOCX/XLSX/CSV, convertir a PDF, **Descargar ZIP**.

## 8. Etiquetas

* **Diseñar** (ingenieros/jefes): agregar texto, campo variable, Code 128, QR, línea, rectángulo,
  imagen PNG; mover con el mouse o flechas (Shift = 5 mm), redimensionar en la esquina, alinear,
  distribuir, capas, bloquear, duplicar (Ctrl+D), deshacer (Ctrl+Z). Ajuste tamaño, DPI **real**
  de la impresora, contador de serial y campos solicitados. Variables `{campo}` y transformaciones.
  La vista previa la genera el servidor con el mismo motor del PDF/ZPL; lo que no cabe se marca en rojo.
* **Publicar versión** (jefes): las impresiones siempre usan una versión publicada.
* **Imprimir**: origen de datos (manual, registros autorizados de un dataset, o un Excel/CSV),
  selección (marcados, rango, todos), copias, destino. «Vista previa» muestra la primera etiqueta con
  datos reales y el total. «Imprimir» pide confirmar la cantidad total.
  * Navegador/PDF: abra el PDF y imprima con **escala 100 % (tamaño real)**, sin márgenes.
  * Impresora registrada: envío directo; el estado será «Aceptado por la cola» o «Estado físico
    desconocido» hasta que confirme en el trabajo que las etiquetas salieron bien.
* **Reimprimir** (jefes): desde el trabajo, con motivo; usa los mismos seriales.
* Validación física: ver `GUIA_VALIDACION_ETIQUETAS.md`.

## 9. Kaizen

1. «Nueva mejora Kaizen»: problema, estado actual, objetivo, área, responsable, prioridad, fechas.
2. Flujo: Propuesta → Evaluación → Aprobada (jefe) → Implementación → Verificación → Cerrada; o
   Rechazada (con motivo). El historial registra autor y fecha.
3. Análisis: 5 porqués, causa raíz, PDCA, resultados. Acciones con responsable y fecha.
4. Antes/después: indicador, unidad, fuente y periodos explícitos. Ahorros con fórmula, cálculo y aprobación de un jefe.
5. «Generar PDF A3».

## 10. Administración

Usuarios (rol, áreas, turno, restablecer contraseña), áreas, turnos, matriz de permisos por rol,
logotipo, diagnóstico, auditoría, impresoras y contadores de serial, datasets.
