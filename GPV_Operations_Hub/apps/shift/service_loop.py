"""Single local background service for the shift portal.

One process (``manage.py run_shift_service`` or the reports scheduler, which calls
:func:`tick`) holds a lease so two copies never run the same cycle at the same time.
It works whether or not anybody has a browser tab open.
"""
import logging
import os
import socket
import time
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

log = logging.getLogger("gpv.shift")
LEASE = "shift-service"


def holder_id():
    return f"{socket.gethostname()}:{os.getpid()}"


def acquire(holder, seconds=180, now=None):
    from apps.core.models import SchedulerLease

    now = now or timezone.now()
    SchedulerLease.objects.get_or_create(name=LEASE)
    got = SchedulerLease.objects.filter(name=LEASE).filter(Q(expires_at__isnull=True) | Q(expires_at__lt=now) | Q(holder=holder)).update(
        holder=holder, expires_at=now + timedelta(seconds=seconds))
    return got == 1


def release(holder):
    from apps.core.models import SchedulerLease

    SchedulerLease.objects.filter(name=LEASE, holder=holder).update(expires_at=None, holder="")


def tick(now=None, client_factory=None):
    """One cycle: due OData syncs (never overlapping), reminders, due report drafts, late-data revisions."""
    from . import odata, services

    now = now or timezone.now()
    out = {"sync": [], "reminders": 0, "reports": []}
    for conn in list(odata.due_connections(now)):
        try:
            run = odata.sync_once(conn, now, client_factory(conn) if client_factory else None)
            out["sync"].append((conn.name, run.status))
        except Exception:  # never let one source stop the service
            log.exception("odata sync crashed for %s", conn.pk)
    try:
        out["reminders"] = services.remind_and_escalate(now)
    except Exception:
        log.exception("reminders failed")
    try:
        out["reports"] = services.generate_due(now)
    except Exception:
        log.exception("report drafts failed")
    return out


def run_loop(stop_after=None, tick_seconds=30):
    holder = holder_id()
    n = 0
    try:
        while True:
            if acquire(holder, seconds=max(tick_seconds * 4, 120)):
                r = tick()
                if r["sync"] or r["reports"]:
                    log.info("shift tick: %s", r)
            else:
                log.info("another shift service holds the lease; waiting")
            n += 1
            if stop_after and n >= stop_after:
                break
            time.sleep(tick_seconds)
    finally:
        release(holder)
