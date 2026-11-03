# Guía del operador · Mi turno

1. **Entre** con su usuario en `http://127.0.0.1:8000/` (en el piloto, en el equipo de la estación).
   Llega directo a **Mi turno**.
2. **Escanee el QR de su estación** (o elíjala en «Cambiar / confirmar contexto») y pulse
   *Confirmar esta estación*. El QR identifica la estación, no a usted.
3. **Escanee o escriba la orden** que va a trabajar. Cambiar de orden pide un motivo.
4. Siga la **frase de «Siguiente acción»**.

## Las 4 acciones

| Botón | Para qué |
|---|---|
| Ver mi trabajo | Meta del turno, buenas confirmadas, manual pendiente, pendiente y eventos recientes |
| Necesito ayuda | Elija el motivo (Falla de equipo, Duda de calidad, Falta material…), comentario/foto opcional, *Enviar*. Verá el estado: Reportado → Recibido → En atención → Resuelto → Verificado |
| Imprimir etiqueta | Elija la plantilla; los datos salen de su estación y orden. El «Enter» del escáner **no** imprime: confirme con el botón |
| Revisar cierre de turno | Pendientes a completar (motivo de paro, comentario de una ayuda) |

## Otras tareas

* **Paros**: *Iniciar paro* al detenerse; *Terminar paro* al reanudar (el motivo puede elegirse al terminar).
* **Materiales**: solicite material faltante; no es un movimiento de inventario.
* **Calidad**: registre una observación; Calidad decide la disposición.
* **Instrucciones**: vea la revisión vigente; *Registrar lectura* no significa estar capacitado.
* **Listas**: marque cada punto; un «No conforme» avisa al equipo responsable.
* **Captura manual** (solo si FactoryLogix no está disponible): queda «pendiente de conciliación» y no suma hasta revisarse.

## Si algo falla

* «Sin conexión: se muestran los últimos datos»: la red o el equipo servidor se detuvo; los números
  no se ponen en cero. Avise al supervisor.
* Si pide ayuda sin red, la solicitud queda guardada en ese navegador y se envía sola al reconectar
  (sin foto). No la repita.
