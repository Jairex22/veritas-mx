# Conciliación entre captura web y FactoryLogix (OData)

La captura web de producción es de **contingencia**. Se guarda como **«Manual pendiente de
conciliación»** y **no** suma a las buenas confirmadas hasta conciliarse o aceptarse.

## Regla aplicada automáticamente

Al guardar una captura manual y en cada sincronización se buscan candidatos automáticos:
misma línea, misma orden, misma operación de conteo y dentro del periodo capturado ±30 min.

| Situación | Resultado | Efecto en el conteo |
|---|---|---|
| Comparten referencia física (lote/panel/etiqueta o serie) **y** misma cantidad y unidad | **Conciliado con OData** | Cuenta solo el registro de OData (80 + 80 del mismo hecho = **80**) |
| Hay candidatos pero sin referencia común (p. ej. misma cantidad) | **Requiere revisión** | No suma hasta que un responsable decida |
| Sin candidatos | Sigue **pendiente** | Visible como «manual pendiente», no confirmado |

La igualdad de cantidades **no** prueba que sea el mismo hecho.

## Revisión por responsable (*Mi turno › Conciliación*, rol supervisor/administrador)

| Decisión | Uso | Conteo |
|---|---|---|
| Es el mismo hecho | Se vincula al registro de OData elegido | No suma (ya está en OData) |
| Es producción adicional | Dos lotes independientes | Suma: 80 + 80 = **160** |
| Rechazar | Captura errónea | No suma |

Toda decisión exige nota, queda en `EventRevision` y en la bitácora de auditoría.

## Reglas de conteo relacionadas

* Solo cuenta la **operación de conteo** de la línea (estación marcada «cuenta como producto
  terminado»). Top y Bottom del mismo panel no se cuentan dos veces.
* Eventos con estación no mapeada **no se cuentan** (se informa el número).
* Reprueba/retest: por serie cuenta el último intento; no agrega piezas. FPY usa el primer intento.
* Paneles → piezas solo con factor de panelización **confirmado**; sin él, «No calculable».
* Snapshot: la captura acumulada más reciente reemplaza a la anterior; nunca se suman.
* La captura manual se registra en la operación de conteo de la línea, aunque se haga desde otra estación.

Implementación: `apps/shift/counting.py` (`reconcile`, `review`, `scope_counts`). Pruebas:
`apps/shift/tests/test_shift.py › CountingTests`.
