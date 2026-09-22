GPV Process Genealogy
======================

A local prototype for visualizing the manufacturing genealogy of an
assembly across SMT -> HM -> MS -> MS1, built for FactoryLogix-style MES
environments. This version runs entirely on DEMO DATA (data/assemblies.json)
- no FactoryLogix, OData, CSV or SQL Server connection yet. The data model
is already shaped so that source can be swapped in later without changing
the frontend.


HOW TO RUN
----------
Requirements: Node.js installed on the machine (nothing else).

    node node/index.js

or double-click:

    START.bat

Then open (it should open automatically):

    http://localhost:3000

To stop the server, press CTRL+C in the console window (or close the
START.bat window).

No "npm install" is required and none of the folders in this project
need it: the compiled/runnable frontend already lives in public/, and
the server only uses Node's built-in http/fs/path/url/child_process
modules - no Express, no bundler, no dev server.

You can copy this whole folder to any other machine that has Node.js
and it will run the same way.


TRY IT
------
In the search box, type one of the demo assembly/part numbers and press
Enter or click SEARCH:

    983306932663201345      (or its part number: MR01400000V)
    FINAL-PRODUCT-0001      (or its part number: FP-9000)
    983306932663201900      (or its part number: MR01400001A)

Click any of the SMT / HM / MS / MS1 cards to see that level's stations,
timing and status.


PROJECT STRUCTURE
------------------
GPV_Process_Genealogy/
|
+-- node/
|   +-- index.js         Server: native http/fs/path/url/child_process only.
|                         Serves /public and the /api/* endpoints below.
|
+-- data/
|   +-- assemblies.json   DEMO DATA. See the "_meta" block inside the file
|                         for the full field-by-field schema. This is the
|                         only place the server reads assembly data from -
|                         swap it for a real integration later without
|                         touching node/index.js's HTTP layer.
|
+-- public/                Already-built frontend - this is what gets served.
|   +-- index.html
|   +-- assets/
|   |   +-- app.js         Same file as src/app.js (see note below).
|   |   +-- app.css        Same file as src/app.css.
|   +-- vendor/
|       +-- react.production.min.js       Vendored React 18 UMD build.
|       +-- react-dom.production.min.js   Vendored ReactDOM 18 UMD build.
|
+-- src/
|   +-- app.js             Canonical, human-authored React source.
|   +-- app.css
|
+-- START.bat              Windows double-click launcher.
+-- README.txt             This file.


WHY THERE IS NO BUILD STEP
---------------------------
src/app.js is written in plain JavaScript using React.createElement
directly (no JSX). Because of that, it is *already* valid code a browser
can run - there is nothing to transpile or bundle. React and ReactDOM are
vendored as their official production UMD builds under public/vendor/ and
loaded as plain <script> tags before app.js in index.html.

public/assets/app.js and public/assets/app.css are exact copies of
src/app.js and src/app.css. If you edit the app, edit the files under
src/ and copy them over public/assets/ (a plain file copy - there is no
compiler involved):

    Windows (from the project folder):
        copy /Y src\app.js public\assets\app.js
        copy /Y src\app.css public\assets\app.css


API ENDPOINTS (read-only, backed by data/assemblies.json)
-----------------------------------------------------------
GET /api/health
    -> { "status": "ok" }

GET /api/assemblies
    -> { "assemblies": [ ...summary of every demo assembly... ] }

GET /api/assemblies/:assembly
    -> full assembly record (matches by assembly number OR part number,
       case-insensitive), or 404 { "error": "Assembly not found" }

GET /api/assemblies/:assembly/route
    -> { assembly, route, currentLevel, levels: [ ...level summaries... ] }

GET /api/assemblies/:assembly/levels/:level
    -> { assembly, partNumber, description, workOrder, level: {...} }

There is no database yet - every request reads data/assemblies.json
directly. All endpoints are GET-only.


DATA MODEL / FUTURE INTEGRATION NOTES
---------------------------------------
Each assembly record already reserves an "avl" object for the AVL /
part-master Excel columns you mentioned (item number, alternative,
manufacturer, MPN, text, obsolete, status, lead free, received lead
free, valid until, temperature, marking, duration). Those fields are
currently null/unpopulated - Work Order, stations and genealogy do NOT
come from that Excel today, only from the demo JSON.

parentAssembly / childAssemblies are also modeled (see
FINAL-PRODUCT-0001 <-> 983306932663201345 in the demo data for a working
example) so the "Related Assemblies" panel has real code behind it, ready
for when genuine parent/child relationships are available from
FactoryLogix - no UI changes should be needed, only real data.


PORT
----
The server listens on port 3000 by default. To use a different port, set
the PORT environment variable before starting it, e.g. on Windows:

    set PORT=4000
    node node/index.js
