"""Print adapters for printers registered by an administrator.

Status semantics (never claims a physical print without evidence):
* GENERATED: output file created (browser/PDF route).
* SENT / UNKNOWN: bytes delivered to a raw TCP port; the physical result is unknown.
* QUEUED: a spooler (Windows/CUPS) accepted the job and returned an identifier.
* CONFIRMED: a person verified the labels on paper.
* FAILED: connection refused / spooler error before any data was accepted.
An ambiguous transmission (error after partial send) is UNKNOWN and is never retried
automatically.
"""
import re
import socket
import subprocess

from django.conf import settings


class PrintResult:
    def __init__(self, status, detail, reference="", evidence=""):
        self.status, self.detail, self.reference, self.evidence = status, detail, reference, evidence


def _timeout():
    return settings.GPV["PRINTER_TIMEOUT"]


def send_tcp(host, port, payload: bytes):
    try:
        sock = socket.create_connection((host, int(port)), timeout=_timeout())
    except OSError as exc:
        return PrintResult("failed", f"No se pudo conectar con la impresora ({host}:{port}): {exc.strerror or exc.__class__.__name__}. "
                                     "No se envió ningún dato.")
    sent = 0
    try:
        sock.settimeout(_timeout())
        view = memoryview(payload)
        while sent < len(payload):
            n = sock.send(view[sent:sent + 65536])
            if n == 0:
                raise OSError("conexión cerrada")
            sent += n
    except OSError as exc:
        return PrintResult("unknown", f"Envío interrumpido tras {sent} de {len(payload)} bytes ({exc.__class__.__name__}). "
                                      "Pudo imprimirse parcialmente: verifique físicamente; no se reimprime automáticamente.",
                           evidence=f"bytes_sent={sent}")
    finally:
        try:
            sock.close()
        except OSError:
            pass
    return PrintResult("unknown", f"Datos entregados al puerto {host}:{port} ({len(payload)} bytes). La conexión correcta no confirma que la "
                                  "etiqueta salió en papel: verifique y confirme.", evidence=f"bytes_sent={sent}")


def query_zebra_status(host, port):
    """~HS host status (Zebra ZPL). Returns dict or None. Does not print."""
    try:
        with socket.create_connection((host, int(port)), timeout=_timeout()) as s:
            s.settimeout(_timeout())
            s.sendall(b"~HS")
            data = b""
            while data.count(b"\x03") < 3:
                chunk = s.recv(1024)
                if not chunk:
                    break
                data += chunk
    except OSError as exc:
        return {"ok": False, "detail": f"Sin conexión: {exc.strerror or exc.__class__.__name__}"}
    text = data.decode("ascii", "replace")
    parts = [p.strip("\x02\x03\r\n") for p in text.split("\x03") if p.strip()]
    if not parts:
        return {"ok": True, "detail": "Conectado; la impresora no respondió a ~HS (puede no ser Zebra/ZPL).", "raw": ""}
    fields = parts[0].split(",")
    flags = {}
    try:
        flags = {"paper_out": fields[1] == "1", "pause": fields[2] == "1"}
        if len(parts) > 1:
            f2 = parts[1].split(",")
            flags["head_open"] = f2[2] == "1" if len(f2) > 2 else None
            flags["ribbon_out"] = f2[3] == "1" if len(f2) > 3 else None
    except IndexError:
        pass
    problems = [k for k, v in flags.items() if v]
    return {"ok": True, "detail": "Estado ZPL: " + (", ".join(problems) if problems else "sin alarmas reportadas"), "flags": flags, "raw": text[:200]}


def send_windows(queue, payload: bytes, title):
    try:
        import win32print  # pywin32 (optional dependency, Windows server only)
    except ImportError:
        return PrintResult("failed", "La cola de Windows requiere el paquete opcional pywin32 en el servidor (requirements-optional.txt).")
    try:
        h = win32print.OpenPrinter(queue)
        try:
            job = win32print.StartDocPrinter(h, 1, (title[:60], None, "RAW"))
            win32print.StartPagePrinter(h)
            win32print.WritePrinter(h, payload)
            win32print.EndPagePrinter(h)
            win32print.EndDocPrinter(h)
        finally:
            win32print.ClosePrinter(h)
    except Exception as exc:
        return PrintResult("failed", f"La cola «{queue}» rechazó el trabajo: {exc}")
    return PrintResult("queued", f"Aceptado por la cola de Windows «{queue}» (trabajo {job}). Estado físico pendiente de confirmar.", reference=str(job))


def send_cups(queue, payload: bytes, title):
    try:
        proc = subprocess.run(["lp", "-d", queue, "-o", "raw", "-t", title[:60]], input=payload, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=_timeout() * 2)
    except FileNotFoundError:
        return PrintResult("failed", "El comando «lp» (CUPS) no está disponible en el servidor.")
    except subprocess.TimeoutExpired:
        return PrintResult("unknown", "La cola no respondió a tiempo; el trabajo pudo haberse aceptado. Verifique antes de reimprimir.")
    if proc.returncode != 0:
        return PrintResult("failed", f"CUPS rechazó el trabajo: {proc.stderr.decode(errors='replace')[:200]}")
    m = re.search(r"request id is (\S+)", proc.stdout.decode(errors="replace"))
    return PrintResult("queued", f"Aceptado por la cola CUPS «{queue}».", reference=m.group(1) if m else "")


def dispatch(printer, payload: bytes, title):
    if not printer.enabled or not printer.validated_at:
        return PrintResult("failed", "La impresión directa está desactivada: la impresora debe validarse y habilitarse por un administrador.")
    if printer.kind == printer.Kind.ZPL_TCP:
        return send_tcp(printer.host, printer.port or 9100, payload)
    if printer.kind == printer.Kind.WINDOWS_QUEUE:
        return send_windows(printer.queue_name, payload, title)
    if printer.kind == printer.Kind.CUPS_QUEUE:
        return send_cups(printer.queue_name, payload, title)
    return PrintResult("failed", "Tipo de impresora sin envío directo.")


def test_connection(printer):
    if printer.kind == printer.Kind.ZPL_TCP:
        if not printer.host or not printer.port:
            return False, "Defina host y puerto."
        st = query_zebra_status(printer.host, printer.port)
        return bool(st and st["ok"]), st["detail"] if st else "Sin respuesta"
    if printer.kind == printer.Kind.WINDOWS_QUEUE:
        try:
            import win32print

            h = win32print.OpenPrinter(printer.queue_name)
            info = win32print.GetPrinter(h, 2)
            win32print.ClosePrinter(h)
            return True, f"Cola encontrada (estado {info.get('Status')}, trabajos {info.get('cJobs')})."
        except ImportError:
            return False, "Requiere pywin32 en el servidor Windows."
        except Exception as exc:
            return False, f"No se pudo abrir la cola: {exc}"
    if printer.kind == printer.Kind.CUPS_QUEUE:
        try:
            proc = subprocess.run(["lpstat", "-p", printer.queue_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=_timeout())
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False, "CUPS no disponible en el servidor."
        return proc.returncode == 0, (proc.stdout or proc.stderr).decode(errors="replace")[:200]
    return True, "Ruta de navegador: no requiere prueba de conexión."
