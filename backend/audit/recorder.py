"""Writing audit logs. The middleware remembers the current request (who, from which IP); record() writes one row.

batch(action, ...): everything recorded inside the block (e.g. the hundreds of class periods one Generate replaces and creates) is
merged into ONE log row, so the list stays readable.
"""
import datetime
import decimal
import uuid
from contextlib import contextmanager
from contextvars import ContextVar

_REQUEST = ContextVar("audit_request", default=None)
_BATCH = ContextVar("audit_batch", default=None)
_SUPPRESS = ContextVar("audit_suppress", default=False)
MAX_ITEMS = 300                 # rows of a bulk change kept in one log entry; the rest is counted


def set_request(request):
    return _REQUEST.set(request)


def reset_request(token):
    _REQUEST.reset(token)


def is_suppressed():
    return _SUPPRESS.get()


@contextmanager
def suppressed():
    """Switch off the per-record signals (the caller records one summary entry itself)."""
    token = _SUPPRESS.set(True)
    try:
        yield
    finally:
        _SUPPRESS.reset(token)


def record_rows(action, entity, ids, texts, *, old=None, new=None):
    """Many rows changed at once: one entry (or one item per row in an open batch)."""
    if _BATCH.get() is not None:
        for pk, text in zip(ids, texts):
            _BATCH.get()["items"].append((action, entity, str(pk), text, None, new if action == "update" else None))
        return None
    ids = [str(i) for i in ids]
    eid = ", ".join(ids[:8]) + (f" (+{len(ids) - 8} more)" if len(ids) > 8 else "")
    summary = f"{len(ids)} {entity} record(s): {texts[0]}" + (" ..." if len(texts) > 1 else "")
    if action == "delete" and old is None:
        old = {"rows": texts[:MAX_ITEMS], "count": len(texts)}
    if action == "create" and new is None:
        new = {"rows": texts[:MAX_ITEMS], "count": len(texts)}
    return record(action, entity, eid, summary=summary, old=old, new=new)


def client_ip(request):
    if request is None:
        return None
    fwd = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    ip = fwd or request.META.get("REMOTE_ADDR") or None
    try:
        import ipaddress
        ipaddress.ip_address(ip)
        return ip
    except (ValueError, TypeError):
        return None


def _actor(request=None, user=None):
    request = request or _REQUEST.get()
    if user is None and request is not None:
        u = getattr(request, "user", None)          # DRF puts the JWT user on the Django request after authentication
        user = u if getattr(u, "is_authenticated", False) else None
    label = ""
    if user is not None:
        label = (user.get_full_name() or "").strip() or user.username
    return user, label, client_ip(request)


def jsonable(v):
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, (datetime.datetime, datetime.date, datetime.time)):
        return v.isoformat()
    if isinstance(v, (decimal.Decimal, uuid.UUID)):
        return str(v)
    if isinstance(v, (list, tuple, set)):
        return [jsonable(x) for x in v]
    if isinstance(v, dict):
        return {str(k): jsonable(x) for k, x in v.items()}
    return str(v)


def record(action, entity, entity_id="", *, summary="", old=None, new=None, user=None, request=None):
    """Write one audit row (or add it to the open batch). Never raises into the caller's work."""
    b = _BATCH.get()
    if b is not None and action in ("create", "delete", "update"):
        b["items"].append((action, entity, str(entity_id), summary, old, new))
        return None
    from django.db import transaction
    from .models import AuditLog
    conn = transaction.get_connection()
    if conn.in_atomic_block and conn.needs_rollback:
        return None                 # the work is being rolled back: nothing was changed, so nothing is logged
    who, label, ip = _actor(request, user)
    try:
        with transaction.atomic():  # a savepoint: an audit problem never breaks the caller's transaction
            return AuditLog.objects.create(user=who, user_label=label[:150], action=action, entity=entity[:60], entity_id=str(entity_id)[:60],
                                           summary=(summary or "")[:300], old_values=jsonable(old), new_values=jsonable(new),
                                           ip_address=ip)
    except Exception:          # an audit problem must never stop the school's work
        import logging
        logging.getLogger(__name__).exception("audit log could not be written")
        return None


@contextmanager
def batch(action, entity, entity_id="", summary="", extra=None):
    """Merge every create / update / delete recorded inside into one row with the given action ("generate", ...)."""
    if _BATCH.get() is not None:              # already inside a batch: the outer one collects
        yield {}
        return
    state = {"items": [], "extra": dict(extra or {}), "summary": summary}
    token = _BATCH.set(state)
    try:
        yield state
    except BaseException:
        _BATCH.reset(token)                   # the work failed (and is rolled back): nothing to record
        raise
    _BATCH.reset(token)
    if not state["items"] and not state.get("force"):
        return
    def text(i):                            # other kinds of record (e.g. the settings row) are named
        return i[3] if i[1] == entity else f"[{i[1]}] {i[3]}"

    def per_entity(kind):
        out = {}
        for i in state["items"]:
            if i[0] == kind:
                out[i[1]] = out.get(i[1], 0) + 1
        return out
    removed = [text(i) for i in state["items"] if i[0] == "delete"]
    added = [text(i) for i in state["items"] if i[0] == "create"]
    changed = [{"record": text(i), "before": i[4], "after": i[5]} for i in state["items"] if i[0] == "update"]
    old = {"removed": removed[:MAX_ITEMS], "removed_count": len(removed), "removed_by_type": per_entity("delete")} if removed else None
    new = {**state["extra"]}
    if added:
        new.update({"added": added[:MAX_ITEMS], "added_count": len(added), "added_by_type": per_entity("create")})
    if changed:
        new.update({"changed": changed[:MAX_ITEMS], "changed_count": len(changed)})
    record(action, entity, entity_id, summary=state["summary"], old=old, new=new or None)
