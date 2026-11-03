"""Shift calendar in America/Mexico_City. A shift whose end time is <= its start time crosses
midnight; its operating date is the date on which it STARTS."""
from datetime import datetime, timedelta

from django.utils import timezone

from apps.core.models import Shift


def window(shift, date):
    """(start, end) aware datetimes for the shift that starts on `date`."""
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(date, shift.start), tz)
    end_date = date + timedelta(days=1) if shift.end <= shift.start else date
    end = timezone.make_aware(datetime.combine(end_date, shift.end), tz)
    return start, end


def breaks(shift, date):
    out = []
    s0, e0 = window(shift, date)
    tz = timezone.get_current_timezone()
    for b in shift.breaks.all():
        d = date if b.start >= shift.start or shift.end > shift.start else date + timedelta(days=1)
        bs = timezone.make_aware(datetime.combine(d, b.start), tz)
        be = timezone.make_aware(datetime.combine(d if b.end > b.start else d + timedelta(days=1), b.end), tz)
        if bs >= s0 and be <= e0:
            out.append((bs, be, b.label))
    return out


def planned_minutes(shift, date):
    s, e = window(shift, date)
    total = (e - s).total_seconds() / 60
    return total - sum((be - bs).total_seconds() / 60 for bs, be, _ in breaks(shift, date))


def current(now=None):
    """(shift, operating_date, start, end) for the instant; None if no shift covers it."""
    now = now or timezone.now()
    local = timezone.localtime(now)
    for shift in Shift.objects.filter(active=True):
        for d in (local.date(), local.date() - timedelta(days=1)):
            s, e = window(shift, d)
            if s <= now < e:
                return shift, d, s, e
    return None


def previous(now=None):
    """The most recent shift that ended before `now`."""
    now = now or timezone.now()
    local = timezone.localtime(now).date()
    best = None
    for shift in Shift.objects.filter(active=True):
        for d in (local, local - timedelta(days=1), local - timedelta(days=2)):
            s, e = window(shift, d)
            if e <= now and (best is None or e > best[3]):
                best = (shift, d, s, e)
    return best


def ended_between(since, until):
    """All (shift, date, start, end) whose end falls in (since, until]. Used to catch up after downtime."""
    out = []
    d = timezone.localtime(since).date() - timedelta(days=1)
    last = timezone.localtime(until).date()
    while d <= last:
        for shift in Shift.objects.filter(active=True):
            s, e = window(shift, d)
            if since < e <= until:
                out.append((shift, d, s, e))
        d += timedelta(days=1)
    return sorted(out, key=lambda x: x[3])
