from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "audit"
    verbose_name = "Audit logs"

    def ready(self):
        from . import signals          # noqa: F401  (connects the save / delete signals)
