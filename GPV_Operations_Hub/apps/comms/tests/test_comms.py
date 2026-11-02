"""Acceptance test 11: announcements, audience, notifications and read confirmation."""
from django.test import Client, TestCase

from apps.comms.models import Announcement, AnnouncementRead
from apps.core.models import Notification, Role
from apps.core.tests.helpers import areas, user


class AnnouncementTests(TestCase):
    def setUp(self):
        self.a = areas()
        self.boss = user("jefe", Role.SUPERVISOR, ("SMT",))
        self.op = user("op", Role.OPERATOR, ("SMT",))
        self.other = user("op_ens", Role.OPERATOR, ("ENS",))

    def client_for(self, u):
        c = Client(HTTP_HOST="127.0.0.1")
        c.force_login(u)
        return c

    def test_11_publish_receive_ack(self):
        r = self.client_for(self.boss).post("/comunicados/nuevo/", {
            "title": "Cambio de procedimiento", "body": "Lea el nuevo instructivo.", "priority": "high",
            "valid_from": "2026-01-01T00:00", "require_ack": "on", "areas": [self.a["SMT"].pk], "roles": ["operator"],
        })
        self.assertEqual(r.status_code, 302, getattr(r, "context", None) and r.context["form"].errors)
        ann = Announcement.objects.get()
        self.assertTrue(Notification.objects.filter(user=self.op, title__contains="Cambio de procedimiento").exists())
        self.assertFalse(Notification.objects.filter(user=self.other).exists())  # other area: not in audience
        c = self.client_for(self.op)
        self.assertContains(c.get("/comunicados/"), "Cambio de procedimiento")
        self.assertEqual(self.client_for(self.other).get(f"/comunicados/{ann.pk}/").status_code, 404)
        poll = c.get("/api/notificaciones/").json()["data"]
        self.assertEqual(poll["unread"], 1)
        c.get(f"/comunicados/{ann.pk}/")
        c.post(f"/comunicados/{ann.pk}/confirmar/")
        rr = AnnouncementRead.objects.get(user=self.op)
        self.assertIsNotNone(rr.ack_at)
        detail = self.client_for(self.boss).get(f"/comunicados/{ann.pk}/")
        self.assertContains(detail, "1 confirmados")
        # operators cannot publish (server-side)
        self.assertEqual(c.post("/comunicados/nuevo/", {"title": "x", "body": "y"}).status_code, 403)

    def test_comments_and_incidents_on_order(self):
        from django.contrib.contenttypes.models import ContentType

        from apps.production.models import WorkOrder

        wo = WorkOrder.objects.create(number="1", area=self.a["SMT"], qty_planned=1)
        ct = ContentType.objects.get_for_model(WorkOrder)
        c = self.client_for(self.op)
        r = c.post("/comunicados/comentarios/", {"ct": ct.pk, "obj": wo.pk, "body": "Falta material", "kind": "incident", "next": f"/produccion/ordenes/{wo.pk}/"})
        self.assertEqual(r.status_code, 302)
        # user from another area cannot comment on it
        r = self.client_for(self.other).post("/comunicados/comentarios/", {"ct": ct.pk, "obj": wo.pk, "body": "x", "next": "/"})
        self.assertEqual(r.status_code, 403)
