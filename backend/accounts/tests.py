from django.test import TestCase
from accounts.models import User



class ComputerStudiesStaffTests(TestCase):
    """Computer Studies = the Dean + the six real teachers; accounts added on top are removed and never topped up again."""

    def _mk(self, sid, first, last, ftype="full_time", dept="Computer Studies"):
        from faculty.models import FacultyProfile
        u = User(school_id=sid, first_name=first, last_name=last, role="faculty", faculty_type=ftype, department=dept)
        u.set_password("x"); u.save()
        FacultyProfile.objects.get_or_create(user=u)
        return u

    def setUp(self):
        from accounts.management.commands.setup_ccs_faculty import PEOPLE
        self.dean = self._mk("D1001", "Anna", "Villanueva", "dean")
        self.real = [self._mk(f"F{2000 + i}", f, l, t) for i, (f, l, t, *_r) in enumerate(PEOPLE)]
        self.extra = [self._mk("F1056", "Maria Cristina", "Dela Cruz"), self._mk("P1045", "Imelda", "Santos", "part_time")]
        self.other = self._mk("F3000", "Lorna", "Reyes", dept="Nursing")

    def test_preview_changes_nothing_and_apply_removes_only_the_extras(self):
        from io import StringIO
        from django.core.management import call_command
        call_command("trim_computer_studies_staff", stdout=StringIO())
        self.assertEqual(User.objects.filter(school_id__in=["F1056", "P1045"]).count(), 2)
        call_command("trim_computer_studies_staff", "--apply", stdout=StringIO())
        self.assertFalse(User.objects.filter(school_id__in=["F1056", "P1045"]).exists())
        self.assertEqual(User.objects.filter(role="faculty", department="Computer Studies").exclude(faculty_type="dean").count(), 6)
        self.assertTrue(User.objects.filter(pk=self.dean.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.other.pk).exists())              # other departments are never touched

    def test_keep_option_and_top_up_skips_computer_studies(self):
        from io import StringIO
        from django.core.management import call_command
        call_command("trim_computer_studies_staff", "--apply", "--keep", "P1045", stdout=StringIO())
        self.assertTrue(User.objects.filter(school_id="P1045").exists())
        self.assertFalse(User.objects.filter(school_id="F1056").exists())
        call_command("add_department_staff", stdout=StringIO())
        self.assertEqual(User.objects.filter(role="faculty", department="Computer Studies").exclude(faculty_type="dean").count(), 7)


class LeadershipNamesTests(TestCase):
    def test_names_change_but_nothing_else(self):
        from io import StringIO
        from django.core.management import call_command
        d = User.objects.create_user(username="DeanNursing", password="NURS", first_name="Old", last_name="Name",
                                     role="faculty", faculty_type="dean", department="Nursing", school_id="DN1")
        p = User.objects.create_user(username="PrincipalJHS", password="JHSPRIN", first_name="X", last_name="Y",
                                     role="principal", school_level="JHS", school_id="PJ1")
        pw = d.password
        call_command("set_leadership_names", stdout=StringIO())
        d.refresh_from_db(); p.refresh_from_db()
        self.assertEqual(d.get_full_name(), "Darwin D. Aznar")
        self.assertEqual(p.get_full_name(), "Sheryl B. Gamboa")
        self.assertEqual((d.password, d.role, d.faculty_type, d.department, d.username, d.school_id),
                         (pw, "faculty", "dean", "Nursing", "DeanNursing", "DN1"))
        from .serializers import UserSerializer
        self.assertEqual(UserSerializer(d).data["full_name"], "Darwin D. Aznar")

    def test_dean_found_by_college_when_login_name_differs(self):
        from io import StringIO
        from django.core.management import call_command
        rt = User.objects.create_user(username="UPHM-D1001", password="x", first_name="Aira", last_name="Gargantos", role="faculty",
                                      faculty_type="dean", department="College of Radiologic Technology", school_id="D1001")
        cba = User.objects.create_user(username="UPHM-D1002", password="x", first_name="Ramon", last_name="Cruz", role="faculty",
                                       faculty_type="dean", department="College of Business Administration",
                                       extra_departments="College of International Hospitality Management", school_id="D1002")
        other = User.objects.create_user(username="UPHM-D1003", password="x", first_name="Keep", last_name="Me", role="faculty",
                                         faculty_type="dean", department="Allied Health", school_id="D1003")
        call_command("set_leadership_names", stdout=StringIO())
        for u in (rt, cba, other):
            u.refresh_from_db()
        self.assertEqual(rt.get_full_name(), "Dr. Noel Juan Acosta")
        self.assertEqual(cba.get_full_name(), "Julius Mesina")
        self.assertEqual(other.get_full_name(), "Keep Me")
        self.assertEqual(rt.username, "UPHM-D1001")


# ---------------------------------------------------------------- "My settings" (accounts/preferences.py)
import io as _io
import os as _os
import shutil as _shutil
import tempfile as _tempfile

from django.test import override_settings
from rest_framework.test import APIClient

def _image(fmt="PNG", size=(900, 600), exif=False):
    from PIL import Image
    img = Image.new("RGB", size, (0, 51, 102))
    out = _io.BytesIO()
    if exif:
        ex = Image.Exif()
        ex[0x010F] = "SecretCameraMaker"          # Make
        ex[0x0131] = "SecretSoftware"             # Software
        img.save(out, fmt, exif=ex.tobytes())
    else:
        img.save(out, fmt)
    return out.getvalue()


def _upload(name, data, ctype):
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile(name, data, content_type=ctype)


class MySettingsTests(TestCase):
    def setUp(self):
        self.media = _tempfile.mkdtemp(prefix="ufast_media_test_")          # a fresh, empty folder for every test
        self._ov = override_settings(MEDIA_ROOT=self.media)
        self._ov.enable()
        self.addCleanup(self._ov.disable)
        self.addCleanup(_shutil.rmtree, self.media, True)
        self.reg = User.objects.create_user(username="UPHM-R9001", password="x", school_id="R9001", role="registrar",
                                            first_name="Rita", last_name="Reyes")
        self.fac = User.objects.create_user(username="UPHM-F9001", password="x", school_id="F9001", role="faculty",
                                            faculty_type="full_time", department="Computer Studies", first_name="Fe", last_name="Cruz")
        self.c = APIClient()
        self.c.force_authenticate(self.fac)

    def test_new_user_gets_the_defaults(self):
        from accounts.models import UserPreference
        self.assertFalse(UserPreference.objects.filter(user=self.fac).exists())
        r = self.c.get("/api/accounts/me/preferences/")
        self.assertEqual(r.status_code, 200)
        p = r.data["preferences"]
        self.assertEqual((p["theme"], p["text_size"], p["table_density"], p["time_format"], p["date_format"], p["landing_page"]),
                         ("light", "medium", "comfortable", "12h", "mdy_short", ""))
        self.assertTrue(p["notify_schedule"])
        self.assertEqual(r.data["profile"]["school_id"], "F9001")
        self.assertFalse(r.data["profile"]["has_picture"])
        self.assertTrue(UserPreference.objects.filter(user=self.fac).exists())

    def test_reads_and_changes_only_own_record(self):
        self.assertEqual(self.c.patch("/api/accounts/me/preferences/", {"first_name": "Felicidad"}, format="json").status_code, 400)
        self.c.patch("/api/accounts/me/preferences/", {"time_format": "24h"}, format="json")
        other = APIClient()
        other.force_authenticate(self.reg)
        r = other.get("/api/accounts/me/preferences/")
        self.assertEqual(r.data["preferences"]["time_format"], "12h")       # the registrar still has the defaults
        self.assertEqual(r.data["profile"]["first_name"], "Rita")
        self.fac.refresh_from_db()
        self.assertEqual(self.fac.first_name, "Fe")                          # the name is not edited from My settings
        # there is no way to name another user: an extra id is refused as an unknown setting
        r = other.patch("/api/accounts/me/preferences/", {"user": self.fac.id, "time_format": "24h"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(APIClient().get("/api/accounts/me/preferences/").status_code, 401)

    def test_invalid_choice_is_rejected(self):
        for body in ({"time_format": "36h"}, {"theme": "neon"}, {"text_size": "huge"}, {"date_format": "yy"},
                     {"email": "not-an-email"}, {"phone": "call me"}, {"first_name": ""}):
            r = self.c.patch("/api/accounts/me/preferences/", body, format="json")
            self.assertEqual(r.status_code, 400, body)
            self.assertTrue(r.data["detail"])

    def test_role_school_id_and_department_cannot_be_changed(self):
        for body in ({"role": "registrar"}, {"school_id": "X1"}, {"department": "Nursing"}, {"username": "x"}):
            r = self.c.patch("/api/accounts/me/preferences/", body, format="json")
            self.assertEqual(r.status_code, 400, body)
        self.fac.refresh_from_db()
        self.assertEqual((self.fac.role, self.fac.school_id, self.fac.department), ("faculty", "F9001", "Computer Studies"))

    def test_landing_page_must_be_allowed_for_the_role(self):
        r = self.c.patch("/api/accounts/me/preferences/", {"landing_page": "generate"}, format="json")   # a Registrar page
        self.assertEqual(r.status_code, 400)
        r = self.c.patch("/api/accounts/me/preferences/", {"landing_page": "availability"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["preferences"]["landing_page"], "availability")
        self.assertEqual([k for k, _ in r.data["choices"]["landing_page"]], ["schedule", "availability"])

    def test_saved_page_the_role_lost_falls_back_to_home(self):
        from accounts.models import UserPreference
        UserPreference.objects.create(user=self.fac, landing_page="generate")
        r = self.c.get("/api/accounts/me/preferences/")
        self.assertEqual(r.data["preferences"]["landing_page"], "")

    def test_notification_switch_hides_that_kind(self):
        from notifications.models import Notification
        Notification.objects.create(recipient=self.fac, notif_type="schedule_update", message="published")
        Notification.objects.create(recipient=self.fac, notif_type="exam_assignment", message="proctor")
        self.assertEqual(self.c.get("/api/notifications/unread_count/").data["unread_count"], 2)
        self.c.patch("/api/accounts/me/preferences/", {"notify_exam": False}, format="json")
        self.assertEqual(self.c.get("/api/notifications/unread_count/").data["unread_count"], 1)
        self.assertEqual(Notification.objects.filter(recipient=self.fac).count(), 2)       # nothing deleted

    # ---- picture
    def _files(self):
        d = _os.path.join(self.media, "profile_pictures")
        return sorted(_os.listdir(d)) if _os.path.isdir(d) else []

    def test_wrong_type_fake_extension_and_too_big_are_rejected(self):
        gif = _upload("me.gif", _image("GIF"), "image/gif")
        self.assertEqual(self.c.post("/api/accounts/me/picture/", {"picture": gif}).status_code, 400)
        fake = _upload("me.png", _image("GIF"), "image/png")                   # a GIF named .png
        r = self.c.post("/api/accounts/me/picture/", {"picture": fake})
        self.assertEqual(r.status_code, 400)
        self.assertIn("JPG, PNG or WebP", r.data["detail"])
        svg = _upload("me.jpg", b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", "image/jpeg")
        self.assertEqual(self.c.post("/api/accounts/me/picture/", {"picture": svg}).status_code, 400)
        big = _upload("big.png", b"\x89PNG\r\n\x1a\n" + b"0" * (2 * 1024 * 1024 + 10), "image/png")
        r = self.c.post("/api/accounts/me/picture/", {"picture": big})
        self.assertEqual(r.status_code, 400)
        self.assertIn("2 MB", r.data["detail"])
        self.assertEqual(self._files(), [])

    def test_valid_picture_is_resized_cleaned_and_stored_under_a_random_name(self):
        from PIL import Image
        from accounts.models import UserPreference
        up = _upload("my holiday photo.jpg", _image("JPEG", (1600, 1200), exif=True), "image/jpeg")
        r = self.c.post("/api/accounts/me/picture/", {"picture": up})
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.data["profile"]["has_picture"])
        self.assertNotIn("picture", r.data["profile"])                          # the file name is never sent
        name = UserPreference.objects.get(user=self.fac).picture
        self.assertRegex(name, r"^[0-9a-f]{32}\.jpg$")
        with Image.open(_os.path.join(self.media, "profile_pictures", name)) as img:
            self.assertLessEqual(max(img.size), 512)
            self.assertEqual(len(img.getexif()), 0)
        f = self.c.get("/api/accounts/me/picture/file/")
        self.assertEqual(f.status_code, 200)
        self.assertEqual(f["Content-Type"], "image/jpeg")
        f.close()
        other = APIClient()
        other.force_authenticate(self.reg)
        self.assertEqual(other.get("/api/accounts/me/picture/file/").status_code, 404)   # only ever the caller's own picture

    def test_replacing_and_removing_deletes_the_old_file(self):
        self.c.post("/api/accounts/me/picture/", {"picture": _upload("a.png", _image("PNG"), "image/png")})
        first = self._files()
        self.c.post("/api/accounts/me/picture/", {"picture": _upload("b.webp", _image("WEBP"), "image/webp")})
        second = self._files()
        self.assertEqual(len(second), 1)
        self.assertNotEqual(first, second)
        r = self.c.delete("/api/accounts/me/picture/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["profile"]["has_picture"])
        self.assertEqual(self._files(), [])
        self.assertEqual(self.c.get("/api/accounts/me/picture/file/").status_code, 404)
