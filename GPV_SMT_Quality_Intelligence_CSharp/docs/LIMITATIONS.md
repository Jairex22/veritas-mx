# Limitaciones conocidas (versión C#)

1. **No ejecutada aún en Windows real.** Se compiló en Linux con destino `win-x64` (el archivo es un PE32+ válido) y se probó en Linux con el mismo código. Falta confirmar en un equipo GPV: arranque, apertura del navegador, botón "Abrir logs" y Administrador de credenciales (P/Invoke).
2. **Ejecutable sin firma digital.** SmartScreen puede advertir y AppLocker/WDAC puede bloquearlo. TI puede firmarlo o autorizarlo; si no, usar la versión Python.
3. **Tamaño:** ~106 MB porque incluye el runtime .NET (no requiere instalación).
4. **Conexión real no probada** contra FactoryLogix (red privada). Escenarios HTTP probados contra un servidor falso local.
5. Resto de limitaciones funcionales iguales a la versión Python (`../GPV_SMT_Quality_Intelligence/docs/LIMITATIONS.md`): tipos de Quality/QualityHistory supuestos hasta leer `$metadata`, mapeo de campos del fixture Mirion, zona horaria de QualityHistory (alerta R09), sin PASS final, línea no verificable en SMT, flujos de proceso y turnos sin configurar, PDF vía impresión del HTML.
