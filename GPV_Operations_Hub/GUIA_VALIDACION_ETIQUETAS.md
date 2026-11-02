# Guía de validación de etiquetas en impresora física

Esta validación **no** se pudo realizar en el entorno de desarrollo (sin impresoras físicas).
Debe ejecutarse en planta antes de usar etiquetas en producción, con un responsable de calidad.
Registre los resultados (fecha, impresora, firmware, DPI, plantilla y versión).

## Plantillas de ejemplo (datos sintéticos)

| Plantilla | Tamaño | DPI | Contenido |
|---|---|---|---|
| Identificación de producto | 50.8 × 25.4 mm (2"×1") | 203 | PN/Rev, Code 128 del serial (contador `serial-producto`), OT y fecha |
| Etiqueta de caja | 101.6 × 76.2 mm (4"×3") | 203 | Cliente, parte (prefijo `GPV-` removido), cantidad, QR, Code 128 de orden y lote, operador solicitado |
| Trazabilidad | 76.2 × 50.8 mm (3"×2") | 300 | QR con serial/parte/OT/lote, Code 128 del serial, texto vertical |

Archivos: `samples/plantillas_etiquetas/*.gpvlabel.json` y datos `samples/etiquetas_datos.csv`.

## 1. Preparación

1. Confirme en la ficha técnica la **resolución real** (203/300/600 DPI). Registre la impresora en
   Administración › Impresoras con ese DPI. No lo infiera del nombre del modelo.
2. Ajuste la plantilla al DPI real (campo DPI del diseñador) y publíquela.
3. Configure el material (ancho/alto de la etiqueta, gap/marca negra) en la impresora o su controlador.
   El portal **no** cambia velocidad, oscuridad ni calibración salvo que el administrador defina esos
   valores explícitamente en la impresora (solo ZPL).

## 2. Ruta navegador / PDF

1. Imprimir › destino «Navegador / PDF» › abra el PDF.
2. En el diálogo de impresión: impresora de etiquetas, **escala 100 % / Tamaño real**, márgenes
   **Ninguno**, tamaño de papel igual a la etiqueta (defínalo en el controlador si no existe).
3. Imprima 3 etiquetas.

## 3. Ruta directa (ZPL por red, solo impresoras compatibles con ZPL)

1. Administración › Impresoras: tipo «Zebra compatible ZPL por red», host/IP y puerto (normalmente 9100) entregados por TI.
2. «Probar conexión» (consulta `~HS`, no imprime). Si es correcto, «Habilitar».
3. Imprima 3 etiquetas. El estado quedará «Estado físico desconocido»: verifique y «Confirmar impresión física».
4. Pruebe una falla controlada (impresora apagada o cable desconectado): el trabajo debe quedar «Fallido» y no reimprimirse solo.

Impresoras CAB u otras marcas: use la ruta navegador/PDF con el controlador del fabricante;
no se envía ZPL por suposición.

## 4. Verificaciones

| # | Prueba | Criterio de aceptación |
|---|---|---|
| 1 | Tamaño | Medir con regla/calibrador: ancho y alto ±0.5 mm respecto al diseño |
| 2 | Alineación | Elementos dentro de márgenes; desplazamiento ≤ 0.5 mm; repetible en 3 etiquetas |
| 3 | Lectura Code 128 | Escáner de planta lee el 100 % en 3 intentos; contenido idéntico al esperado (ej. `000123`) |
| 4 | Lectura QR | Lector/teléfono decodifica el texto completo (ej. `S=T00000001|PN=…`) |
| 5 | Zona de silencio | Espacio en blanco a ambos lados del Code 128 ≥ 10 módulos (≈3.3 mm con módulo 0.33 mm) |
| 6 | Módulo | Ancho de barra mínima visible y uniforme; sin barras fundidas (ajuste oscuridad en la impresora si aplica) |
| 7 | Texto | Legible, sin cortes; acentos y Ñ correctos |
| 8 | Consecutivos | Dos usuarios imprimiendo a la vez obtienen seriales distintos y continuos |
| 9 | Reimpresión | Requiere permiso y motivo; conserva seriales; queda en historial |
| 10 | Calidad de impresión | Si hay verificador ISO/IEC 15416/15415 disponible, registrar grado (≥ C recomendado) |

## 5. Verificación automática previa (sin impresora)

El sistema ya decodifica sus propios códigos con un lector independiente (`zxing-cpp`) en la prueba
automatizada `apps/labels/tests/test_labels.py` (PDF renderizado a 600 DPI). Esto valida la
codificación y geometría, **no** la impresión física.
