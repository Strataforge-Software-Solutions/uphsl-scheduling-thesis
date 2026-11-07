"""Every create / update / delete of a record in the school's data, with the values before and after.

Covered: the apps below (accounts, curriculum, faculty, rooms, engine, exams, basic_ed), except the models in SKIP (logs, computed
records and personal display settings). Bulk changes do not send these signals; the Schedule table records its own bulk changes
(engine.models.ScheduleQuerySet), and Generate is grouped into one entry (recorder.batch).
"""
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver

from . import recorder

APPS = {"accounts", "curriculum", "faculty", "rooms", "engine", "exams", "basic_ed"}
SKIP = {"engine.log", "engine.conflictlog", "accounts.userpreference", "basic_ed.conflictrecord", "basic_ed.scheduleevent",
        "faculty.coveragesuggestion", "faculty.workloadrecord"}
IGNORE_FIELDS = {"password", "last_login", "updated_at", "generated_at", "created_at", "submitted_at", "date_joined"}


def tracked(model):
    if recorder.is_suppressed():
        return False
    meta = model._meta
    return meta.app_label in APPS and f"{meta.app_label}.{meta.model_name}" not in SKIP and not meta.auto_created


def entity_name(model):
    meta = model._meta
    return f"SHS/JHS {meta.verbose_name}" if meta.app_label == "basic_ed" else str(meta.verbose_name)


def snapshot(obj):
    """{field: value} of one record; a link to another record is {"id", "name"} so the log stays readable."""
    out = {}
    for f in obj._meta.concrete_fields:
        if f.name in IGNORE_FIELDS or f.primary_key:
            continue
        if f.is_relation:
            rid = getattr(obj, f.attname)
            if rid is None:
                out[f.name] = None
                continue
            try:
                name = str(getattr(obj, f.name))
            except Exception:
                name = ""
            out[f.name] = {"id": rid, "name": name[:120]}
        else:
            out[f.name] = recorder.jsonable(getattr(obj, f.attname))
    lv = school_level(obj)
    if lv:
        out["level"] = lv
    return out


def school_level(obj):
    """SHS / JHS records: their school level (on the record, or on its section / teacher / timetable), so each level's admin view
    lists only its own records. None for college records."""
    if obj._meta.app_label != "basic_ed":
        return None
    for path in ("level", "section.level", "faculty.level", "run.level"):
        cur = obj
        try:
            for part in path.split("."):
                cur = getattr(cur, part)
        except Exception:
            continue
        if cur in ("SHS", "JHS"):
            return cur
    return None


def _label(obj):
    try:
        return str(obj)[:300]
    except Exception:
        return ""


@receiver(pre_save)
def _remember_old(sender, instance, raw=False, **kw):
    if raw or not tracked(sender) or instance.pk is None:
        return
    old = sender._base_manager.filter(pk=instance.pk).first()
    instance._audit_old = snapshot(old) if old is not None else None


@receiver(post_save)
def _saved(sender, instance, created, raw=False, **kw):
    if raw or not tracked(sender):
        return
    new = snapshot(instance)
    if created or getattr(instance, "_audit_old", None) is None:
        recorder.record("create", entity_name(sender), instance.pk, summary=_label(instance), new=new)
        return
    old = instance._audit_old
    changed = [k for k in new if old.get(k) != new.get(k)]
    instance._audit_old = new
    if changed:
        keep = changed + (["level"] if "level" in new and "level" not in changed else [])     # the level stays on SHS/JHS entries
        recorder.record("update", entity_name(sender), instance.pk, summary=_label(instance),
                        old={k: old.get(k) for k in keep}, new={k: new.get(k) for k in keep})


@receiver(post_delete)
def _deleted(sender, instance, **kw):
    if tracked(sender):
        recorder.record("delete", entity_name(sender), instance.pk, summary=_label(instance), old=snapshot(instance))


@receiver(m2m_changed)
def _links(sender, instance, action, pk_set=None, model=None, **kw):
    """e.g. a teacher's specializations added or removed."""
    if action not in ("post_add", "post_remove", "post_clear") or not tracked(type(instance)):
        return
    field = next((f.name for f in type(instance)._meta.many_to_many if f.remote_field.through is sender), "links")
    names = sorted(str(x) for x in model.objects.filter(pk__in=pk_set or [])) if model is not None and pk_set else []
    word = {"post_add": "added", "post_remove": "removed", "post_clear": "cleared"}[action]
    recorder.record("update", entity_name(type(instance)), instance.pk, summary=_label(instance),
                    new={field: {word: names or "all"}})
