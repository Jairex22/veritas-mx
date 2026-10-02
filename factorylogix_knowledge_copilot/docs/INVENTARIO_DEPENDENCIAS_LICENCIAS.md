# Inventario de dependencias y licencias

> Generado por `scripts/generate_docs.py` a partir de los paquetes instalados en el entorno de pruebas (Linux, Python 3.11.15). Las versiones en Windows pueden variar dentro de los rangos de `requirements.txt`. Validar con el área legal antes de producción.

| Paquete | Versión probada | Licencia | Tipo |
|---|---|---|---|
| numpy | 2.4.6 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | directa |
| openpyxl | 3.1.5 | MIT License | directa |
| pandas | 3.0.6 | BSD License | directa |
| pypdf | 6.19.0 | BSD-3-Clause | directa |
| python-docx | 1.2.0 | MIT License | directa |
| PyYAML | 6.0.1 | MIT License | directa |
| requests | 2.34.2 | Apache Software License | directa |
| streamlit | 1.64.0 | Apache-2.0 | directa |
| altair | 6.3.0 | BSD License | transitiva |
| anyio | 4.14.1 | MIT | transitiva |
| attrs | 26.1.0 | MIT | transitiva |
| certifi | 2026.6.17 | Mozilla Public License 2.0 (MPL 2.0) | transitiva |
| charset-normalizer | 3.4.9 | MIT | transitiva |
| click | 8.4.2 | BSD-3-Clause | transitiva |
| colorama | 0.4.6 | BSD License | transitiva |
| et_xmlfile | 2.0.0 | MIT License | transitiva |
| h11 | 0.16.0 | MIT License | transitiva |
| httptools | 0.8.0 | MIT | transitiva |
| idna | 3.18 | BSD-3-Clause | transitiva |
| itsdangerous | 2.2.0 | BSD License | transitiva |
| Jinja2 | 3.1.6 | BSD License | transitiva |
| jsonschema | 4.26.0 | MIT | transitiva |
| jsonschema-specifications | 2025.9.1 | MIT | transitiva |
| lxml | 6.1.3 | BSD-3-Clause | transitiva |
| MarkupSafe | 3.0.3 | BSD-3-Clause | transitiva |
| narwhals | 2.26.0 | MIT | transitiva |
| packaging | 24.0 | Apache Software License, BSD License | transitiva |
| pillow | 12.3.0 | MIT-CMU | transitiva |
| protobuf | 7.36.2 | 3-Clause BSD License | transitiva |
| pyarrow | 25.0.1 | Apache-2.0 | transitiva |
| pydeck | 0.9.3 | Apache License 2.0 | transitiva |
| python-dateutil | 2.9.0.post0 | BSD License, Apache Software License | transitiva |
| python-multipart | 0.0.32 | Apache-2.0 | transitiva |
| referencing | 0.37.0 | MIT | transitiva |
| rpds-py | 2026.6.3 | MIT | transitiva |
| six | 1.16.0 | MIT License | transitiva |
| starlette | 1.3.1 | BSD-3-Clause | transitiva |
| toml | 0.10.2 | MIT License | transitiva |
| typing_extensions | 4.16.0 | PSF-2.0 | transitiva |
| urllib3 | 2.7.0 | MIT | transitiva |
| uvicorn | 0.50.2 | BSD-3-Clause | transitiva |
| watchdog | 6.0.0 | Apache Software License | transitiva |
| websockets | 16.1.1 | BSD-3-Clause | transitiva |

## Componentes opcionales (no incluidos)

| Componente | Licencia | Uso |
|---|---|---|
| sentence-transformers + torch + modelo multilingüe | Apache-2.0 / BSD (verificar modelo) | Embeddings semánticos locales |
| Tesseract OCR + pytesseract | Apache-2.0 | OCR de imágenes escaneadas |
| Ollama / llama.cpp | MIT | LLM local opcional (verificar licencia del modelo elegido) |

No se usan servicios de nube, API de OpenAI ni API de Claude.
