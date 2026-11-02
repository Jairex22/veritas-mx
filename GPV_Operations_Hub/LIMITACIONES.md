# Limitaciones conocidas y dependencias externas

Este documento declara lo que **no** hace la versión 1.0.0 o lo que depende de elementos externos.
No hay botones «próximamente»: lo no soportado se rechaza con un mensaje que indica la alternativa.

## Formatos de entrada

| Formato | Soporte |
|---|---|
| XLSX, CSV (UTF-8, Windows-1252, ISO-8859-1; `,` `;` tab `|`) | Soportados y probados |
| XLS, XLSB, ODS | No soportados: se pide guardarlos como XLSX/CSV |
| XLSM, DOCM, PPTM y cualquier archivo con `vbaProject.bin` | Rechazados (macros nunca se ejecutan) |
| DOC, PPT | No soportados: guardar como DOCX/PPTX |
| BarTender `.btw` | **No** compatible. Plantillas propias `gpv-label/1` (JSON) |

## Importación y fórmulas de Excel

* openpyxl no calcula fórmulas. Se usa el **valor almacenado** por Excel (marcado como posiblemente
  desactualizado). Si no hay valor almacenado, se calcula con el motor interno **solo** para el
  subconjunto soportado; si no es posible, la fila se rechaza (nunca se convierte en 0).
* Fórmulas matriciales, nombres definidos y referencias a libros externos no se evalúan.
* Seriales guardados como número con más de 15 dígitos o en notación científica: se detectan y
  rechazan; los dígitos perdidos **no** se pueden recuperar.
* En modo lectura en flujo (para archivos grandes) no se detectan celdas combinadas al importar.
* Durante una importación grande en curso, los indicadores muestran una advertencia; los datos del lote
  se hacen visibles por bloques (cada bloque es atómico; si falla, se compensa todo el lote).

## Hoja de cálculo

* Funciones soportadas: SUMA/SUM, PROMEDIO/AVERAGE, MIN, MAX, CONTAR/COUNT, CONTARA/COUNTA, SI/IF,
  SUMAR.SI/SUMIF, CONTAR.SI/COUNTIF, BUSCARV/VLOOKUP (exacta y aproximada), BUSCARX/XLOOKUP (solo
  coincidencia exacta, con «si no se encuentra»), Y/AND, O/OR, NO/NOT, REDONDEAR/ROUND, ABS,
  SI.ERROR/IFERROR. Operadores `+ - * / ^ & = <> < > <= >= %`. Cualquier otra función → `#NAME?`.
* Separador decimal en fórmulas: punto. Argumentos con `,` o `;`.
* Fechas: se guardan como texto ISO; no hay aritmética de fechas.
* Ordenar un rango que contiene fórmulas se bloquea (cambiaría su significado).
* Formato condicional básico (>, <, =, >=, <=, contiene) y validación (lista, número con rango).
* Gráficos, imágenes, comentarios y formato condicional de un XLSX importado no se cargan en la
  hoja: se informa antes de editar y el archivo original se conserva.
* Diálogos de formato condicional, validación y tabla dinámica usan cuadros de diálogo simples del navegador.

## Documentos

* La extracción de tablas de PDF es aproximada (pdfplumber) y requiere capa de texto.
* OCR solo si Tesseract está instalado en el servidor (opcional; no incluido).
* Conversión DOCX/PPTX/XLSX→PDF, miniaturas de PPTX/DOCX y corte de Word por páginas físicas
  requieren **LibreOffice** en el servidor. Fidelidad sujeta a fuentes instaladas.
* PPTX: notas del orador y comentarios **no** se copian en diapositivas duplicadas o combinadas
  (se avisa); vínculos entre diapositivas de presentaciones distintas se eliminan al combinar.
* DOCX combinado: estilos ausentes, numeración/listas, notas al pie, comentarios, encabezados y
  propiedades de sección del documento añadido pueden perder formato (se avisa).
* «Recortar márgenes» cambia la CropBox: **no** es censura segura.
* Transformar un PDF firmado invalida la firma; los formularios pueden perder interactividad al combinar.
* La compresión es sin pérdida por defecto; la recompresión de imágenes es opcional y con pérdida.
* XLSX: duplicar o combinar hojas no copia gráficos ni imágenes (limitación de openpyxl; se avisa).

## Etiquetas e impresión

* Códigos soportados: Code 128 (codificador propio verificado con zxing-cpp) y QR (segno).
  **Data Matrix y GS1 no están implementados.**
* Rotaciones de 0/90/180/270°. Fuente Helvetica (métricas comunes a SVG/PDF); en ZPL se usa la
  fuente escalable `^A0`, por lo que el ancho del texto puede diferir ligeramente.
* ZPL: los códigos usan comandos nativos (`^BC` con códigos de invocación explícitos, `^BQ`);
  imágenes como `^GFA`; líneas diagonales aproximadas con `^GD`.
* Ruta navegador: genera PDF del tamaño exacto; el usuario imprime con escala 100 %. El navegador
  no imprime silenciosamente ni elige impresora USB.
* Impresión directa: TCP 9100 (ZPL), cola de Windows (requiere `pywin32` en el servidor) o CUPS.
  **No validado con impresoras físicas** en este entorno: siga `GUIA_VALIDACION_ETIQUETAS.md`.
* CAB u otras marcas: sin lenguaje nativo implementado; use su controlador con la ruta PDF.
* Un envío TCP correcto queda como «Estado físico desconocido» hasta que una persona confirma.
* Los consecutivos pueden tener huecos si un trabajo falla tras reservar (nunca duplicados).

## Plataforma

* SQLite es para demostración o uso reducido (bloqueo de escritura único). Para uso compartido use PostgreSQL.
* Modo de trabajos `inline` (local): los trabajos corren dentro de la solicitud; sin cancelación efectiva
  a mitad de un paso. Use `worker` en despliegue.
* Notificaciones por consulta periódica (no WebSockets); no hay correo ni mensajería externa.
* Interfaz en español; código y logs técnicos en inglés.
* No hay integración con FactoryLogix, Dynamics, correo o servidores de GPV: solo archivos y capturas.
* Sin acceso a infraestructura corporativa, no se probó: PostgreSQL real, IIS/HTTPS, servicio de
  Windows, LibreOffice en Windows, impresoras físicas ni carga con cientos de usuarios.
