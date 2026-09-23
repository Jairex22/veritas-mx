GPV PRODUCT CONFIGURATION  v1.0
===============================

Visor de escritorio (Python 3 + tkinter/ttk) para el libro de validacion de
marcado SMT "EMX-KA661_Rev.0 Validacion de marcado SMT (1).xlsm".


1. EJECUTAR
-----------
- Doble clic en START.bat   (usa "py" y, si no existe, "python").
- O desde consola:          python GPV_Product_Configuration.py
- Reporte de datos sin GUI: python GPV_Product_Configuration.py --check MR01400000V

Requisitos: Python 3.8+ de python.org (tkinter viene incluido).
openpyxl es OPCIONAL: si no esta instalado, la app usa su lector interno
(zipfile + xml.etree) y obtiene exactamente los mismos datos.


2. ESTRUCTURA
-------------
GPV_Product_Configuration/
  GPV_Product_Configuration.py   aplicacion
  START.bat                      lanzador Windows (rutas relativas)
  README.txt
  config/settings.json           configuracion (rutas relativas a esta carpeta)
  data/<archivo>.xlsm            Excel fuente (SOLO LECTURA)
  logs/app.log                   bitacora: cargas, hojas, filas, busquedas, errores

La carpeta completa se puede mover: todas las rutas se resuelven con
Path(__file__).resolve().parent.


3. EXCEL - SOLO LECTURA
-----------------------
- La app nunca escribe ni guarda el .xlsm; las macros no se tocan.
- En cada carga (y en cada RELOAD / F5) se copia el archivo a una carpeta
  temporal y se lee esa copia, asi Excel puede tenerlo abierto y ingenieria
  puede actualizarlo mientras la app esta abierta.
- Si settings.json apunta a un archivo inexistente y en data/ hay un solo
  .xlsm/.xlsx, se usa ese.


4. ATAJOS
---------
Enter    Buscar (compatible con escaner de codigo de barras)
F5       Recargar Excel desde disco
Escape   Limpiar busqueda
Ctrl+F   Ir al buscador
Ctrl+Q   Cerrar
Doble clic en alternativa -> VIEW DETAILS filtrado por ese Item number


5. BUSQUEDA
-----------
Campos: Item number (Part number), Assembly/Parent (si existiera) y MPN.
No distingue mayusculas/minusculas e ignora espacios sobrantes.
Prioridad: coincidencia exacta > "empieza con" > "contiene" (min. 3 caracteres).


6. MODOS
--------
ENGINEERING: toda la informacion, fuente (hoja/fila), material, campos extra.
PRODUCTION : solo alternativas utilizables (Status/Stopped distinto de "Yes"),
             Item / Alternative / Manufacturer / MPN / Marking.


7. ARBOL BOM
------------
El Excel no contiene columnas Parent/Level/Assembly, por eso el arbol es una
LOGICAL VIEW:  Item number -> Alternativas -> Manufacturer / MPN / Marking.
NO es una genealogia real de FactoryLogix. Si en el futuro el libro trae
columnas Parent o Level con datos, la app arma el arbol real automaticamente.


8. SETTINGS.JSON
----------------
excel_file            ruta relativa del Excel
default_mode          ENGINEERING | PRODUCTION
window_width/height   tamano inicial (se ajusta a la pantalla)
reader                auto | openpyxl | builtin
max_tree_items        items maximos listados en busquedas parciales
details_max_rows      filas maximas mostradas en VIEW DETAILS
extra_column_aliases  aliases adicionales, ej. {"mpn": ["mfr part"]}


9. NOTA SOBRE EL CONTENIDO DEL EXCEL ENTREGADO
----------------------------------------------
- Hoja AVL (tabla "MyGrid", A1:M48090): 48,089 filas, pero solo la columna
  "Item number" tiene valores; Alternative, Manufacturer, Type, Text, Obsolete,
  Stopped, Lead free, Received lead free, Valid until, Temperature, Marking y
  Duration estan vacias en esta copia.
- Hoja Start: resultado pegado por la macro para MR01400000V (4 alternativas
  A1-A4 con datos completos).
- Segun la macro Fetch_Details, AVL "Type" = MPN y AVL "Stopped" = Status.
  Status "Yes" = NO USAR (G2 = O); ninguna alternativa en "Yes" = USAR (G2 = P).
Cuando se use un Excel con la hoja AVL completa, la app mostrara todas las
alternativas, fabricantes, MPN y marcados sin cambiar el codigo.
