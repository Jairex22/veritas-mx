"""Persistent job queue.

* ``enqueue()`` stores a :class:`Job`. With ``GPV_JOBS_MODE=inline`` (demo default) the job
  runs immediately inside the request; with ``worker`` it waits for ``manage.py run_worker``.
* Claiming uses an atomic conditional UPDATE, valid for SQLite and PostgreSQL, so two
  workers never run the same job.
* Stale ``running`` jobs (no heartbeat) are re-queued or failed by :func:`recover_stale_jobs`.
"""
import logging
import os
import socket
import traceback
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .logging_utils import new_op_id, reset_op_id, set_op_id
from .models import Job

log = logging.getLogger("gpv.jobs")

HANDLERS = {}


class JobCancelled(Exception):
    pass


class UserFacingError(Exception):
    """Error whose message is safe and useful for the end user (Spanish)."""


def job_handler(kind):
    def decorator(func):
        HANDLERS[kind] = func
        return func

    return decorator


class JobContext:
    def __init__(self, job):
        self.job = job
        self._last_pct = -1

    @property
    def params(self):
        return self.job.params

    @property
    def user(self):
        return self.job.created_by

    def progress(self, pct, message=""):
        pct = max(0, min(100, int(pct)))
        if pct == self._last_pct and not message:
            return
        self._last_pct = pct
        Job.objects.filter(pk=self.job.pk).update(progress=pct, message=message[:300], heartbeat=timezone.now())
        self.check_cancel()

    def check_cancel(self):
        if Job.objects.filter(pk=self.job.pk, cancel_requested=True).exists():
            raise JobCancelled()


def worker_id():
    return f"{socket.gethostname()}:{os.getpid()}"


def enqueue(kind, params=None, user=None, idempotency_key=None, run_inline=None):
    """Create a job. Returns (job, created). A repeated idempotency key returns the existing job."""
    if kind not in HANDLERS:
        raise ValueError(f"No handler registered for job kind {kind}")
    if idempotency_key:
        existing = Job.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            return existing, False
    try:
        with transaction.atomic():
            job = Job.objects.create(
                kind=kind,
                params=params or {},
                created_by=user if (user is not None and user.is_authenticated) else None,
                idempotency_key=idempotency_key or None,
            )
    except IntegrityError:
        return Job.objects.get(idempotency_key=idempotency_key), False
    inline = settings.GPV["JOBS_MODE"] == "inline" if run_inline is None else run_inline
    if inline:
        if claim(job.pk, "inline"):
            execute(Job.objects.get(pk=job.pk))
        job.refresh_from_db()
    return job, True


def claim(job_id, holder):
    now = timezone.now()
    updated = Job.objects.filter(pk=job_id, status=Job.Status.QUEUED, cancel_requested=False).update(
        status=Job.Status.RUNNING, locked_by=holder, started=now, heartbeat=now
    )
    return updated == 1


def claim_next(holder):
    candidates = Job.objects.filter(status=Job.Status.QUEUED).order_by("created").values_list("pk", flat=True)[:10]
    for pk in candidates:
        if claim(pk, holder):
            return Job.objects.get(pk=pk)
    return None


def execute(job):
    """Run a claimed job and persist its final state."""
    handler = HANDLERS.get(job.kind)
    Job.objects.filter(pk=job.pk).update(attempts=job.attempts + 1)
    token = set_op_id(f"job-{str(job.pk)[:8]}")
    try:
        if handler is None:
            raise UserFacingError(f"Tipo de trabajo no soportado: {job.kind}")
        ctx = JobContext(job)
        result = handler(ctx) or {}
        Job.objects.filter(pk=job.pk).update(
            status=Job.Status.SUCCEEDED, progress=100, result=result, finished=timezone.now(), error=""
        )
        log.info("job %s %s succeeded", job.kind, job.pk)
    except JobCancelled:
        Job.objects.filter(pk=job.pk).update(status=Job.Status.CANCELLED, finished=timezone.now(), message="Cancelado por el usuario")
        log.info("job %s %s cancelled", job.kind, job.pk)
    except UserFacingError as exc:
        Job.objects.filter(pk=job.pk).update(status=Job.Status.FAILED, finished=timezone.now(), error=str(exc)[:4000])
        log.warning("job %s %s failed: %s", job.kind, job.pk, exc)
    except Exception as exc:  # unexpected: keep trace in logs, show friendly message
        op = new_op_id()
        log.error("job %s %s crashed [ref %s]: %s\n%s", job.kind, job.pk, op, exc, traceback.format_exc())
        Job.objects.filter(pk=job.pk).update(
            status=Job.Status.FAILED,
            finished=timezone.now(),
            error=f"Error interno al procesar el trabajo. Referencia para soporte: {op}. Intente de nuevo o contacte al administrador.",
        )
    finally:
        reset_op_id(token)


def recover_stale_jobs(stale_minutes=15):
    """Re-queue jobs whose worker died; fail them after JOB_MAX_ATTEMPTS."""
    limit = timezone.now() - timedelta(minutes=stale_minutes)
    max_attempts = settings.GPV["JOB_MAX_ATTEMPTS"]
    recovered = 0
    for job in Job.objects.filter(status=Job.Status.RUNNING, heartbeat__lt=limit):
        if job.attempts >= max_attempts:
            Job.objects.filter(pk=job.pk, status=Job.Status.RUNNING).update(
                status=Job.Status.FAILED,
                finished=timezone.now(),
                error="El trabajo se interrumpió (servidor o trabajador detenido) y superó los reintentos.",
            )
        else:
            Job.objects.filter(pk=job.pk, status=Job.Status.RUNNING).update(status=Job.Status.QUEUED, locked_by="")
        recovered += 1
    return recovered


def job_payload(job):
    return {
        "id": str(job.pk),
        "kind": job.kind,
        "status": job.status,
        "status_label": job.get_status_display(),
        "progress": job.progress,
        "message": job.message,
        "error": job.error,
        "result": job.result if job.status == Job.Status.SUCCEEDED else {},
        "final": job.is_final,
        "created": timezone.localtime(job.created).isoformat(),
    }
