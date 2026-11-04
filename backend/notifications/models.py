from django.conf import settings
from django.db import models


class Notification(models.Model):
    TYPES = [
        ("schedule_update", "Schedule Update"),
        ("conflict_alert", "Conflict Alert"),
        ("exam_assignment", "Exam Assignment"),
        ("substitute_assignment", "Substitute Assignment"),
    ]

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    notif_type = models.CharField(max_length=30, choices=TYPES)
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
