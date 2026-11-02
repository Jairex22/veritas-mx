# Avisos de terceros

El portal no incluye bibliotecas JavaScript, CSS, fuentes ni iconos de terceros: la interfaz,
los gráficos SVG, la cuadrícula de la hoja, el diseñador de etiquetas, el codificador Code 128 y
los iconos son código propio de este proyecto. Se usa la fuente del sistema (Segoe UI en Windows).

Dependencias de Python (instaladas desde PyPI; no se redistribuyen dentro del ZIP):

| Paquete | Versión | Licencia | Uso |
|---|---|---|---|
| Django | 5.2.18 | BSD-3-Clause | Framework web |
| asgiref | 3.12.1 | BSD-3-Clause | Dependencia de Django |
| sqlparse | 0.5.5 | BSD-3-Clause | Dependencia de Django |
| tzdata | 2026.5 | Apache-2.0 | Zonas horarias (Windows) |
| openpyxl | 3.1.5 | MIT | XLSX |
| et_xmlfile | 2.0.0 | MIT | Dependencia de openpyxl |
| pypdf | 6.21.1 | BSD-3-Clause | PDF |
| cryptography | 50.0.2 | Apache-2.0 o BSD-3-Clause | PDF cifrados |
| cffi | 2.1.1 | MIT-0 | Dependencia de cryptography |
| pycparser | 3.12 | BSD-3-Clause | Dependencia de cffi |
| pypdfium2 | 5.13.0 | Apache-2.0 / BSD-3-Clause (incluye PDFium, BSD-3-Clause) | Miniaturas, PDF a imagen |
| pdfplumber | 0.11.10 | MIT | Tablas de PDF |
| pdfminer.six | 20260107 | MIT | Dependencia de pdfplumber |
| charset-normalizer | 3.5.2 | MIT | Dependencia |
| reportlab | 5.0.1 | BSD-3-Clause | PDF de reportes, A3 y etiquetas |
| pillow | 12.3.0 | MIT-CMU | Imágenes |
| python-docx | 1.2.0 | MIT | Word |
| python-pptx | 1.0.2 | MIT | PowerPoint |
| XlsxWriter | 3.3.1 | BSD-2-Clause | Dependencia de python-pptx |
| lxml | 6.1.3 | BSD-3-Clause | XML |
| typing_extensions | 4.16.0 | PSF-2.0 | Dependencia |
| segno | 1.6.6 | BSD-3-Clause | QR |

Opcionales: waitress 3.0.2 (ZPL-2.1), zxing-cpp 3.1.1 (Apache-2.0), psycopg 3.2.13 (LGPL-3.0, uso
como biblioteca dinámica sin modificación), pywin32 (PSF).

Motores externos opcionales, instalados por TI en el servidor y no incluidos: LibreOffice (MPL-2.0),
Tesseract OCR (Apache-2.0). Herramienta solo de desarrollo: Playwright (Apache-2.0) para la prueba E2E.

Las licencias se verificaron en los metadatos de PyPI el 2026-11-02. Ninguna dependencia del núcleo
requiere suscripción comercial ni claves de servicios externos.
