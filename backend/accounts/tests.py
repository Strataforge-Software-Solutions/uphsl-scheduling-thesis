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
