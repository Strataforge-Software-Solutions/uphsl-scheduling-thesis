"""Derived data that must follow the schedules it describes. Called after class or exam schedules are deleted so nothing stale is left
behind (conflict log lines for classes that no longer exist, notifications about schedules that are gone). Curriculum, faculty, rooms and
accounts are never touched."""
from .models import ConflictLog, Schedule


def cleanup_after_delete():
    from exams.models import ExamSchedule
    from notifications.models import Notification
    out = {"conflict_logs": 0, "notifications": 0}
    if not Schedule.objects.exists():
        out["conflict_logs"] = ConflictLog.objects.all().delete()[0]
        out["notifications"] += Notification.objects.filter(notif_type__in=["schedule_update", "conflict_alert", "substitute_assignment"]).delete()[0]
    else:
        live = Schedule.objects.values_list("section_id", flat=True).distinct()
        out["conflict_logs"] = ConflictLog.objects.filter(section__isnull=False).exclude(section_id__in=live).delete()[0]
    if not ExamSchedule.objects.exists():
        out["notifications"] += Notification.objects.filter(notif_type="exam_assignment").delete()[0]
    return out
