"""Acceptance test 13: scheduled report generated once even if the scheduler retries."""
import threading
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.core.models import Job, Notification, Role
from apps.core.tests.helpers import areas, user
from apps.reports.models import ReportRun, ReportSchedule
from apps.reports.services import next_occurrence, scheduler_tick

MX = ZoneInfo("America/Mexico_City")


class ScheduleTests(TestCase):
    def setUp(self):
        areas()
        self.sup = user("sup", Role.SUPERVISOR, ("SMT",))
        self.sch = ReportSchedule.objects.create(name="Diario", kind="daily", frequency="daily", time_of_day=time(6, 30), formats=["pdf", "xlsx"],
                                                 created_by=self.sup, filters={"period": "today"})
        self.sch.recipients.add(self.sup)

    def test_next_occurrence_in_mexico_city(self):
        after = datetime(2026, 11, 2, 7, 0, tzinfo=MX)
        nxt = next_occurrence(self.sch, after)
        self.assertEqual(nxt.astimezone(MX), datetime(2026, 11, 3, 6, 30, tzinfo=MX))
        self.sch.frequency, self.sch.weekday = "weekly", 4
        self.assertEqual(next_occurrence(self.sch, after).astimezone(MX).date().isoformat(), "2026-11-06")

    def test_13_runs_once_even_with_retries(self):
        due = timezone.now() - timedelta(minutes=1)
        ReportSchedule.objects.filter(pk=self.sch.pk).update(next_run_at=due)
        created = scheduler_tick()
        self.assertEqual(len(created), 1)
        # the scheduler "retries" the same occurrence (e.g. crashed before updating next_run_at)
        ReportSchedule.objects.filter(pk=self.sch.pk).update(next_run_at=due)
        again = scheduler_tick()
        self.assertEqual(again, [])
        self.assertEqual(ReportRun.objects.filter(schedule=self.sch).count(), 1)
        run = ReportRun.objects.get(schedule=self.sch)
        self.assertEqual(run.status, ReportRun.Status.DONE)  # inline job mode in tests
        self.assertEqual(set(run.outputs.values_list("fmt", flat=True)), {"pdf", "xlsx"})
        self.assertTrue(Notification.objects.filter(user=self.sup, title__contains="Reporte generado").exists())
        self.assertEqual(Job.objects.filter(kind="reports.generate").count(), 1)

    def test_missed_occurrences_collapse_to_one(self):
        ReportSchedule.objects.filter(pk=self.sch.pk).update(next_run_at=timezone.now() - timedelta(days=3, hours=1))
        created = scheduler_tick()
        self.assertEqual(len(created), 1)
        self.assertGreaterEqual(created[0].params.get("_skipped_missed_occurrences", 0), 2)
        self.sch.refresh_from_db()
        self.assertGreater(self.sch.next_run_at, timezone.now())

    def test_all_formats_and_templates_generate(self):
        from apps.reports.services import create_run, generate_run

        for kind in ("daily", "weekly", "late", "quality", "by_line", "kaizen"):
            run = generate_run(create_run(kind, {"period": "all"}, self.sup, ["pdf", "xlsx", "csv", "docx", "pptx"]))
            self.assertEqual(run.status, "done", run.error)
            self.assertEqual(run.outputs.count(), 5)


class ConcurrentSchedulerTests(TransactionTestCase):
    def test_two_schedulers_same_occurrence(self):
        areas()
        sup = user("sup2", Role.SUPERVISOR, ("SMT",))
        sch = ReportSchedule.objects.create(name="X", kind="late", frequency="daily", time_of_day=time(5), formats=["csv"], created_by=sup,
                                            next_run_at=timezone.now() - timedelta(minutes=2))
        errors = []

        def worker():
            try:
                scheduler_tick()
            except Exception as exc:  # pragma: no cover
                errors.append(exc)
            finally:
                connection.close()

        ts = [threading.Thread(target=worker) for _ in range(3)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(ReportRun.objects.filter(schedule=sch).count(), 1)
