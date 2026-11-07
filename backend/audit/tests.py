"""Audit logs: who / what / when / before-after / IP are recorded; nobody can change or delete a log; only the IT Admin reads them."""
import datetime

from django.utils import timezone

from accounts.models import User
from engine.models import Schedule, Section
from engine.tests import Base, SY

from .models import AuditLog, AuditLogImmutable


class AuditLogTests(Base):
    def setUp(self):
        self.admin = User.objects.create_user(username="itadmin", password="pw", school_id="ITA", role="admin", first_name="Ivy", last_name="Admin")

    def test_an_edit_records_who_what_before_after_and_ip(self):
        row = self.row(teacher=self.teachers[0], h=7)
        Schedule.objects.filter(pk=row.pk).update(term="1st Sem")
        AuditLog.objects.all()                                                # (read only: nothing to clear)
        self.client.force_authenticate(self.dean)
        r = self.client.patch(f"/api/engine/schedules/{row.pk}/", {"teacher": self.teachers[1].id}, format="json", REMOTE_ADDR="10.0.0.7")
        self.assertEqual(r.status_code, 200, r.data)
        log = AuditLog.objects.filter(action="update", entity="schedule", entity_id=str(row.pk)).first()
        self.assertIsNotNone(log)
        self.assertEqual((log.user_id, log.user_label, log.ip_address), (self.dean.id, "Dean T", "10.0.0.7"))
        self.assertEqual(log.old_values["teacher"]["id"], self.teachers[0].id)
        self.assertEqual(log.new_values["teacher"]["id"], self.teachers[1].id)

    def test_login_is_recorded_without_the_password(self):
        r = self.client.post("/api/accounts/login/", {"username": "itadmin", "password": "pw"}, format="json", REMOTE_ADDR="10.1.2.3")
        self.assertEqual(r.status_code, 200)
        log = AuditLog.objects.get(action="login")
        self.assertEqual((log.user_id, log.ip_address), (self.admin.id, "10.1.2.3"))
        self.assertNotIn("pw", str(log.new_values) + str(log.old_values) + log.summary)

    def test_generate_is_one_entry_with_the_replaced_and_new_periods(self):
        before = AuditLog.objects.count()
        r = self.gen()
        self.assertEqual(r.status_code, 201, r.data)
        made = AuditLog.objects.all()[: AuditLog.objects.count() - before]
        gens = [x for x in made if x.action == "generate"]
        self.assertEqual(len(gens), 1)
        self.assertEqual(gens[0].new_values["added_by_type"]["schedule"], Schedule.objects.count())
        self.assertFalse([x for x in made if x.entity == "schedule" and x.action == "create"])     # not one row per period
        self.gen()                                                             # again: the drafts it replaced are listed
        last = AuditLog.objects.filter(action="generate").first()
        self.assertTrue(last.old_values["removed_by_type"]["schedule"] > 0)

    def test_bulk_approve_is_one_update_entry(self):
        ids = [self.row(teacher=self.teachers[0], h=h).pk for h in (7, 8)]
        Schedule.objects.filter(pk__in=ids).update(term="1st Sem")
        self.client.force_authenticate(self.dean)
        r = self.client.post("/api/engine/schedules/approve_bulk/", {"ids": ids, "to_status": "approved"}, format="json")
        self.assertEqual(Schedule.objects.filter(pk__in=ids, status="approved").count(), 2, r.data)
        logs = list(AuditLog.objects.filter(action="update", entity="schedule", new_values__status="approved"))
        self.assertEqual(len(logs), 1)                                          # one entry for the whole Approve
        self.assertEqual(logs[0].user_id, self.dean.id)
        self.assertEqual(len(logs[0].old_values["rows"]), 2)

    def test_logs_cannot_be_changed_or_deleted(self):
        log = AuditLog.objects.create(action="create", entity="test", entity_id="1")
        log.summary = "changed"
        with self.assertRaises(AuditLogImmutable):
            log.save()
        with self.assertRaises(AuditLogImmutable):
            log.delete()
        with self.assertRaises(AuditLogImmutable):
            AuditLog.objects.filter(pk=log.pk).update(summary="x")
        with self.assertRaises(AuditLogImmutable):
            AuditLog.objects.filter(pk=log.pk).delete()
        self.assertEqual(AuditLog.objects.get(pk=log.pk).summary, "")
        # the API has no way to write either, not even for the IT Admin
        self.client.force_authenticate(self.admin)
        for method in ("post", "put", "patch", "delete"):
            self.assertEqual(getattr(self.client, method)("/api/audit/logs/", {}, format="json").status_code, 405, method)

    def test_only_the_it_admin_reads_them_and_the_filters_work(self):
        Section.objects.create(name="Z9", program=self.prog, year_level="1st Year", semester="1st Sem")      # a "system" create
        self.client.force_authenticate(self.dean)
        self.row(teacher=self.teachers[0], h=9)
        self.assertEqual(self.client.get("/api/audit/logs/").status_code, 403)
        self.client.force_authenticate(self.registrar)
        self.assertEqual(self.client.get("/api/audit/logs/").status_code, 403)
        AuditLog.objects.create(user=self.dean, user_label="Dean T", action="update", entity="schedule", entity_id="5", summary="moved")
        self.client.force_authenticate(self.admin)
        d = self.client.get("/api/audit/logs/").data
        self.assertGreater(d["count"], 0)
        self.assertIn({"id": self.dean.id, "label": "Dean T"}, d["users"])
        d = self.client.get("/api/audit/logs/", {"user": self.dean.id, "action": "update"}).data
        self.assertTrue(d["results"]) and self.assertTrue(all(x["user_id"] == self.dean.id and x["action"] == "update" for x in d["results"]))
        today = timezone.localdate()
        self.assertGreater(self.client.get("/api/audit/logs/", {"date_from": today.isoformat(), "date_to": today.isoformat()}).data["count"], 0)
        tomorrow = (today + datetime.timedelta(days=1)).isoformat()
        self.assertEqual(self.client.get("/api/audit/logs/", {"date_from": tomorrow}).data["count"], 0)
        self.assertEqual(self.client.get("/api/audit/logs/", {"action": "hack"}).status_code, 400)
        self.assertEqual(self.client.get("/api/audit/logs/", {"date_from": "yesterday"}).status_code, 400)
        system = self.client.get("/api/audit/logs/", {"user": "system"}).data
        self.assertTrue(all(x["user"] == "System" for x in system["results"]))

    def test_removing_an_account_keeps_its_logs(self):
        u = User.objects.create_user(username="temp", password="pw", school_id="TMP", role="registrar", first_name="Tem", last_name="P")
        AuditLog.objects.create(user=u, user_label="Tem P", action="login", entity="user", entity_id=str(u.pk))
        u.delete()
        self.assertTrue(AuditLog.objects.filter(user_label="Tem P", action="login").exists())


_ = SY


class LevelAuditLogTests(Base):
    """The SHS / JHS admin view lists only that level's records and its own principal / teachers."""

    def test_level_filter(self):
        from basic_ed import models as bm
        admin = User.objects.create_user(username="itadm2", password="pw", school_id="ITB", role="admin")
        shs_t = User.objects.create_user(username="shst", password="pw", school_id="S1", role="teacher", school_level="SHS", first_name="Sam", last_name="H")
        jhs_p = User.objects.create_user(username="jhsp", password="pw", school_id="J1", role="principal", school_level="JHS", first_name="Joy", last_name="P")
        fac = bm.Faculty.objects.create(user=shs_t, level="SHS", employee_id="S1", specializations="Math")
        fac.max_weekly_hours = 20
        fac.save()                                                             # an SHS update: keeps its level on the entry
        self.client.post("/api/accounts/login/", {"username": "jhsp", "password": "pw"}, format="json")
        self.row(teacher=self.teachers[0], h=7)                                # a college record
        self.client.force_authenticate(admin)
        shs = self.client.get("/api/audit/logs/", {"level": "SHS"}).data["results"]
        jhs = self.client.get("/api/audit/logs/", {"level": "JHS"}).data["results"]
        self.assertTrue(any(x["entity"] == "SHS/JHS faculty" and x["action"] == "update" for x in shs))
        self.assertFalse(any(x["entity"] == "schedule" for x in shs + jhs))      # no college records in a level view
        self.assertTrue(any(x["action"] == "login" and x["user"] == "Joy P" for x in jhs))
        self.assertFalse(any(x["action"] == "login" for x in shs))
        self.assertEqual(self.client.get("/api/audit/logs/", {"level": "ABC"}).status_code, 400)
        everything = self.client.get("/api/audit/logs/").data["results"]
        self.assertTrue(any(x["entity"] == "schedule" for x in everything))      # the College admin view still sees all
