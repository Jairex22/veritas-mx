GPV PRODUCT CONFIGURATION  v1.0
===============================

Visor de escritorio (Python 3 + tkinter/ttk) para el libro de validacion de
marcado SMT "EMX-KA661_Rev.0 Validacion de marcado SMT (1).xlsm".


1. EJECUTAR
-----------
- Doble clic en START.bat   (usa "py" y, si no existe, "python").
- O desde consola:          python GPV_Product_Configuration.py
- Reporte de datos sin GUI: python GPV_Product_Configuration.py --check MR01400000V --raw ROHM --mark 0

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
Enter    Ejecuta la busqueda de la barra que tiene el foco (compatible con escaner)
F2       Ir a MARKING VALIDATION
F3       Ir a RAW MATERIALS
Ctrl+F   Ir a la busqueda BOM
F5       Recargar Excel desde disco (re-ejecuta las 3 busquedas activas)
Escape   Limpia solo la seccion que tiene el foco
Ctrl+Q   Cerrar


5. TRES BUSQUEDAS INDEPENDIENTES (no se mezclan)
------------------------------------------------
Todas: sin distinguir mayusculas, ignoran espacios sobrantes,
prioridad exacta > "empieza con" > "contiene" (min. 3 caracteres).

a) BOM / ASSEMBLY (arriba, "Assembly / Top Level" + SEARCH BOM)
   Solo columnas Item number / Assembly. Construye BOM STRUCTURE.
   Si el valor es un MPN o un marking, solo muestra una sugerencia.

b) RAW MATERIALS (barra propia)
   Item number, MPN, Manufacturer, Alternative, Description/Text.
   Tabla de resultados (una fila por fila del Excel) + detalle completo.
   No cambia el BOM; el boton SHOW ITEM IN BOM lo hace solo si se pide.

c) MARKING VALIDATION (segmento propio, borde verde)
   Busqueda INVERSA en la columna "Marking": el operador escanea o escribe
   lo que lee en el componente y la app lista TODAS las filas con ese marking.
   Estados:
     READY FOR SCAN
     MARKING FOUND                  coincidencia exacta, alternativa utilizable
     MARKING FOUND - DON'T USE      todas las coincidencias tienen Status = Yes
     NO EXACT MATCH - PARTIAL       solo coincidencias parciales: VERIFICAR
     MARKING NOT FOUND
   Exacta = igual sin mayusculas/espacios extra, o igual sin ningun espacio.
   Si una celda Marking tiene varias opciones (una por linea o separadas por
   ; , |) cada opcion se compara por separado.
   MATCH DETAIL muestra Expected marking, Item, MPN, Manufacturer,
   Alternative, Description, Status, Obsolete y si pertenece al BOM buscado.
   Cada validacion queda registrada en logs/app.log.


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
- Solo 2 filas tienen Marking: "0" (A1 MCR10EZHJ000) y "RC0805JR-070RL  YAGE" (A2).
Cuando se use un Excel con la hoja AVL completa, la app mostrara todas las
alternativas, fabricantes, MPN y marcados sin cambiar el codigo.
