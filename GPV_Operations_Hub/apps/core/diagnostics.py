"""System diagnostics shared by the web page and ``manage.py gpv_diagnose``."""
import platform
import sys
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


def _item(name, status, detail, fix=""):
    return {"name": name, "status": status, "detail": detail, "fix": fix}


def check_database():
    items = []
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        vendor = connection.vendor
        items.append(_item("Base de datos", "ok", f"Conectada ({vendor})."))
        if vendor == "sqlite" and not settings.DEBUG:
            items.append(_item("Motor de base de datos", "warn", "SQLite en perfil de producción.",
                               "Para uso multiusuario configure PostgreSQL (DESPLIEGUE_INTERNO.md)."))
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if plan:
            items.append(_item("Migraciones", "error", f"{len(plan)} migraciones pendientes.", "Ejecute: manage.py migrate"))
        else:
            items.append(_item("Migraciones", "ok", "Todas aplicadas."))
    except Exception as exc:
        items.append(_item("Base de datos", "error", f"Sin conexión: {exc.__class__.__name__}", "Revise GPV_DB_* en .env"))
    return items


def check_folders():
    items = []
    for label, path in [
        ("Archivos privados", settings.PRIVATE_MEDIA_ROOT),
        ("Temporales", settings.TEMP_DIR),
        ("Respaldos", settings.BACKUP_DIR),
        ("Logs", settings.LOG_DIR),
    ]:
        probe = path / f".probe-{uuid.uuid4().hex}"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            items.append(_item(f"Carpeta: {label}", "ok", f"Escritura correcta en {path}"))
        except OSError as exc:
            items.append(_item(f"Carpeta: {label}", "error", f"No se puede escribir en {path}: {exc.strerror}",
                               "Otorgue permisos de escritura a la cuenta que ejecuta el servidor."))
    static_css = settings.BASE_DIR / "static" / "gpv" / "css" / "app.css"
    items.append(_item("Recursos estáticos", "ok" if static_css.exists() else "error",
                       "CSS/JS locales presentes." if static_css.exists() else "Falta static/gpv/css/app.css",
                       "" if static_css.exists() else "Vuelva a descomprimir el paquete completo."))
    return items


def check_converters():
    from apps.documents.engines import office_engine_status, ocr_engine_status, pdf_raster_status

    items = []
    st = office_engine_status()
    items.append(_item("Convertidor Office (LibreOffice)", "ok" if st["available"] else "warn", st["detail"],
                       "" if st["available"] else st["requirement"]))
    st = pdf_raster_status()
    items.append(_item("Render de PDF (pypdfium2)", "ok" if st["available"] else "warn", st["detail"]))
    st = ocr_engine_status()
    items.append(_item("OCR (opcional, Tesseract)", "ok" if st["available"] else "info", st["detail"],
                       "" if st["available"] else st["requirement"]))
    try:
        import zxingcpp  # noqa: F401

        items.append(_item("Lector de códigos (zxing-cpp, opcional)", "ok", "Disponible para verificar códigos generados."))
    except ImportError:
        items.append(_item("Lector de códigos (zxing-cpp, opcional)", "info", "No instalado.",
                           "Opcional: pip install -r requirements-optional.txt"))
    return items


def check_jobs():
    from .models import Job, SchedulerLease

    items = []
    mode = settings.GPV["JOBS_MODE"]
    queued = Job.objects.filter(status=Job.Status.QUEUED).count()
    running = Job.objects.filter(status=Job.Status.RUNNING).count()
    failed_24 = Job.objects.filter(status=Job.Status.FAILED, finished__gte=timezone.now() - timedelta(hours=24)).count()
    if mode == "inline":
        items.append(_item("Trabajos", "info", f"Modo inline (demostración): se ejecutan dentro de la solicitud. En cola: {queued}.",
                           "Para uso compartido use GPV_JOBS_MODE=worker y mantenga activo manage.py run_worker."))
    else:
        oldest = Job.objects.filter(status=Job.Status.QUEUED).order_by("created").first()
        stuck = oldest and oldest.created < timezone.now() - timedelta(minutes=5)
        items.append(_item("Trabajos", "warn" if stuck else "ok",
                           f"Modo worker. En cola: {queued}, en proceso: {running}.",
                           "Hay trabajos esperando más de 5 min: verifique que run_worker esté activo." if stuck else ""))
    items.append(_item("Trabajos fallidos (24 h)", "warn" if failed_24 else "ok", str(failed_24)))
    lease = SchedulerLease.objects.filter(name="reports").first()
    if lease and lease.expires_at and lease.expires_at > timezone.now():
        items.append(_item("Planificador de reportes", "ok", f"Activo ({lease.holder}), vence {timezone.localtime(lease.expires_at):%H:%M:%S}."))
    else:
        items.append(_item("Planificador de reportes", "warn", "No hay un planificador activo.",
                           "Si usa reportes programados mantenga activo: manage.py run_scheduler"))
    return items


def check_printers():
    from apps.labels.models import Printer

    items = []
    for p in Printer.objects.all():
        if p.kind == Printer.Kind.BROWSER:
            items.append(_item(f"Impresora: {p.name}", "ok", "Ruta navegador/PDF (sin envío directo)."))
            continue
        status = "ok" if (p.enabled and p.validated_at) else "warn"
        detail = f"{p.get_kind_display()} · {'habilitada' if p.enabled else 'deshabilitada'} · " + (
            f"validada {timezone.localtime(p.validated_at):%Y-%m-%d %H:%M}" if p.validated_at else "sin validar")
        items.append(_item(f"Impresora: {p.name}", status, detail,
                           "" if status == "ok" else "Pruebe la conexión y habilítela en Administración › Impresoras."))
    if not items:
        items.append(_item("Impresoras", "info", "No hay impresoras registradas.", "Solo disponible la ruta navegador/PDF."))
    return items


def check_runtime():
    items = [
        _item("Python", "ok" if sys.version_info >= (3, 11) else "error", platform.python_version(),
              "" if sys.version_info >= (3, 11) else "Se requiere Python 3.11 a 3.13."),
        _item("Zona horaria", "ok", f"{settings.TIME_ZONE} (almacenamiento en UTC). Hora local: {timezone.localtime():%Y-%m-%d %H:%M:%S}"),
        _item("Modo depuración", "warn" if settings.DEBUG else "ok",
              "DEBUG activo (solo desarrollo)." if settings.DEBUG else "DEBUG desactivado.",
              "En despliegue use GPV_ENV=prod." if settings.DEBUG else ""),
        _item("Datos de demostración", "warn" if settings.GPV["ALLOW_DEMO"] and not settings.DEBUG else "ok",
              "Permitidos" if settings.GPV["ALLOW_DEMO"] else "Deshabilitados"),
    ]
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo("America/Mexico_City")
    except Exception:
        items.append(_item("Base de zonas horarias", "error", "No se encontró America/Mexico_City.", "Instale el paquete tzdata (requirements.txt)."))
    return items


def run_all():
    sections = [
        ("Ejecución", check_runtime),
        ("Base de datos", check_database),
        ("Carpetas y recursos", check_folders),
        ("Convertidores", check_converters),
        ("Trabajos y planificador", check_jobs),
        ("Impresión", check_printers),
    ]
    out = []
    for title, func in sections:
        try:
            out.append({"title": title, "items": func()})
        except Exception as exc:
            out.append({"title": title, "items": [_item(title, "error", f"No se pudo verificar: {exc.__class__.__name__}: {exc}")]})
    return out
