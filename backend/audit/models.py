"""Audit logs: who did what, when, to which record, the values before and after, and from which IP address.

Append-only. A log row can be written once and never changed or deleted, by anybody (the IT Admin included):
  * here: save() refuses an existing row, delete() refuses, and the QuerySet refuses update() / delete() / bulk_update();
  * in PostgreSQL (the real database): a trigger refuses UPDATE, DELETE and TRUNCATE on the table (migration 0001);
  * in the API: the endpoint is GET only, and only the IT Admin may read it.
"""
from django.conf import settings
from django.db import models


class AuditLogImmutable(Exception):
    pass


class AuditLogQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise AuditLogImmutable("Audit logs cannot be changed.")

    def delete(self):
        raise AuditLogImmutable("Audit logs cannot be deleted.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise AuditLogImmutable("Audit logs cannot be changed.")


class AuditLog(models.Model):
    ACTIONS = [("create", "Create"), ("update", "Update"), ("delete", "Delete"), ("login", "Login"), ("generate", "Generate")]

    # who: the account id, plus the name at that moment (an account renamed or removed later keeps its history readable).
    # No database constraint and DO_NOTHING: removing an account never touches (or is blocked by) its logs.
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.DO_NOTHING, db_constraint=False,
                             related_name="+")
    user_label = models.CharField(max_length=150, blank=True, default="")
    action = models.CharField(max_length=10, choices=ACTIONS, db_index=True)
    entity = models.CharField(max_length=60, db_index=True)               # e.g. "schedule", "faculty profile", "section"
    entity_id = models.CharField(max_length=60, blank=True, default="")   # e.g. "12" (several: "12, 13, 14")
    summary = models.CharField(max_length=300, blank=True, default="")    # readable one-liner: "CS101 CS1 Mon 7:00-8:00"
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = AuditLogQuerySet.as_manager()

    class Meta:
        ordering = ["-timestamp", "-id"]
        default_permissions = ("view",)          # no add / change / delete permission exists for anybody

    def save(self, *args, **kwargs):
        if self.pk is not None and AuditLog.objects.filter(pk=self.pk).exists():
            raise AuditLogImmutable("Audit logs cannot be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AuditLogImmutable("Audit logs cannot be deleted.")

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.user_label or 'system'} {self.action} {self.entity} {self.entity_id}"
