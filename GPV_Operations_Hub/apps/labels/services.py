"""Label printing workflow: serial reservation, job creation (idempotent), output and dispatch."""
import io

from django.db import IntegrityError, transaction
from django.db.models import F, Max
from django.utils import timezone

from apps.core.audit import audit
from apps.core.files import store_generated
from apps.core.jobs import UserFacingError

from . import printing
from .models import PrintEvent, PrintJob, Printer, SerialCounter
from .render import TemplateError, base_values, to_pdf, to_zpl

MAX_LABELS_PER_JOB = 5000


def reserve_serials(counter_name, n):
    """Reserve n consecutive values atomically. Safe with concurrent requests:
    the conditional UPDATE serialises writers (row lock in PostgreSQL, write lock in SQLite)."""
    if n <= 0:
        return []
    with transaction.atomic():
        updated = SerialCounter.objects.filter(name=counter_name).update(next_value=F("next_value") + n, updated=timezone.now())
        if not updated:
            raise UserFacingError(f"El contador de seriales «{counter_name}» no existe.")
        c = SerialCounter.objects.get(name=counter_name)
        end = c.next_value  # value after increment
    start = end - n
    return [f"{c.prefix}{str(v).zfill(c.pad)}" for v in range(start, end)]


def expand_labels(template, records, prompts, copies, serials):
    """One entry per physical label: each record gets its own serial (shared by its copies)."""
    labels = []
    k = 0
    for idx, rec in enumerate(records, start=1):
        serial = serials[idx - 1] if serials else None
        for cp in range(1, copies + 1):
            k += 1
            labels.append(base_values(rec, prompts, serial=serial, index=k, copy_no=cp))
    return labels


def _event(job, status, detail, user=None):
    PrintEvent.objects.create(job=job, status=status, detail=detail[:500], user=user)


def create_and_print(user, version, records, prompts, copies, printer, idempotency_key, source="", reprint_of=None, reprint_reason=""):
    if not idempotency_key or len(idempotency_key) > 120:
        raise UserFacingError("Solicitud sin identificador; recargue la página.")
    existing = PrintJob.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        return existing, False  # double click / retry of the same submission
    template = version.definition
    copies = int(copies)
    if copies < 1 or copies > 100:
        raise UserFacingError("Copias por registro: entre 1 y 100.")
    if not records:
        raise UserFacingError("No hay registros seleccionados para imprimir.")
    total = len(records) * copies
    if total > MAX_LABELS_PER_JOB:
        raise UserFacingError(f"El trabajo tendría {total} etiquetas; el máximo por trabajo es {MAX_LABELS_PER_JOB}.")
    if printer is not None and printer.is_direct:
        if not (printer.enabled and printer.validated_at):
            raise UserFacingError("La impresora seleccionada no está validada/habilitada para envío directo.")
        if printer.language == Printer.Language.ZPL and not printer.dpi:
            raise UserFacingError("La impresora no tiene DPI registrado; un administrador debe configurarlo.")
    # serials: reuse original serials on reprint, otherwise reserve new ones
    if reprint_of is not None:
        serials = list(reprint_of.serials)
        if len(serials) != len(records) and serials:
            raise UserFacingError("La reimpresión debe usar los mismos registros del trabajo original.")
    elif template.get("serial_counter"):
        serials = reserve_serials(template["serial_counter"], len(records))
    else:
        serials = []
    labels = expand_labels(template, records, prompts, copies, serials)
    try:
        pdf, warnings = to_pdf(template, labels)
        zpl = None
        if printer is not None and printer.language == Printer.Language.ZPL:
            zpl, w2 = to_zpl(template, labels, printer)
            warnings += w2
    except TemplateError as exc:
        raise UserFacingError(str(exc))
    job = None
    for _attempt in range(5):
        try:
            with transaction.atomic():
                number = (PrintJob.objects.aggregate(m=Max("number"))["m"] or 0) + 1
                job = PrintJob.objects.create(
                    number=number, template_version=version, printer=printer if (printer and printer.is_direct) else None,
                    route="direct" if (printer and printer.is_direct) else "browser", records_count=len(records), copies=copies,
                    total_labels=total, data=[{k: v for k, v in lbl.items()} for lbl in labels[:MAX_LABELS_PER_JOB]], serials=serials,
                    source=source[:200], user=user, idempotency_key=idempotency_key, reprint_of=reprint_of, reprint_reason=reprint_reason[:300],
                )
            break
        except IntegrityError:
            dup = PrintJob.objects.filter(idempotency_key=idempotency_key).first()
            if dup:
                return dup, False  # concurrent double submission: the first one wins
    if job is None:
        raise UserFacingError("No se pudo registrar el trabajo de impresión; intente de nuevo.")
    stamp = timezone.localtime().strftime("%Y%m%d_%H%M%S")
    job.output_pdf = store_generated(pdf, f"etiquetas_{job.number}_{stamp}.pdf", user)
    if zpl is not None:
        job.output_zpl = store_generated(zpl, f"etiquetas_{job.number}_{stamp}.zpl", user)
    job.evidence = "\n".join(sorted(set(warnings)))[:4000]
    job.save()
    _event(job, PrintJob.Status.GENERATED, f"Generado: {total} etiquetas ({len(records)} registros × {copies} copias). Plantilla {version}.", user)
    if job.route == "direct":
        payload = zpl if zpl is not None else pdf
        job.status = PrintJob.Status.SENT
        job.sent_at = timezone.now()
        job.save(update_fields=["status", "sent_at"])
        _event(job, PrintJob.Status.SENT, f"Enviando a {printer.name}", user)
        res = printing.dispatch(printer, payload, f"GPV etiquetas #{job.number}")
        job.status = {"failed": PrintJob.Status.FAILED, "queued": PrintJob.Status.QUEUED, "unknown": PrintJob.Status.UNKNOWN}[res.status]
        job.queue_reference = res.reference
        if res.status == "failed":
            job.error = res.detail
        job.save(update_fields=["status", "queue_reference", "error"])
        _event(job, job.status, res.detail + (f" [{res.evidence}]" if res.evidence else ""), user)
    audit(user, "labels.print" if reprint_of is None else "labels.reprint", job,
          f"Etiquetas #{job.number}: {total} uds, {version}, {'impresora ' + printer.name if job.route == 'direct' else 'PDF/navegador'}, estado {job.get_status_display()}"
          + (f", reimpresión de #{reprint_of.number}: {reprint_reason}" if reprint_of else ""))
    return job, True


def confirm(job, user, ok, note=""):
    if job.status in (PrintJob.Status.CONFIRMED,):
        raise UserFacingError("El trabajo ya está confirmado.")
    job.status = PrintJob.Status.CONFIRMED if ok else PrintJob.Status.FAILED
    if ok:
        job.confirmed_by, job.confirmed_at = user, timezone.now()
    else:
        job.error = (note or "Marcado como fallido por el usuario")[:500]
    job.save()
    _event(job, job.status, ("Confirmado físicamente" if ok else "Marcado como fallido") + (f": {note}" if note else ""), user)
    audit(user, "labels.confirm" if ok else "labels.mark_failed", job, f"Trabajo #{job.number}: {job.get_status_display()} {note}")
