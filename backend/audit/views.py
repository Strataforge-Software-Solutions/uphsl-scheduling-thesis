"""GET /api/audit/logs/ -- READ-ONLY list for the IT Admin. There is no endpoint that creates, changes or deletes a log.

Filters: ?user=<id> (or "system"), ?action=create|update|delete|login|generate, ?date_from=YYYY-MM-DD, ?date_to=YYYY-MM-DD (Asia/Manila
days, both included), ?entity=..., ?q=<text in the record / summary>, ?page=1 (50 per page).
"""
import datetime

from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import AuditLog

PAGE_SIZE = 50


def _is_admin(user):
    return bool(getattr(user, "is_authenticated", False) and getattr(user, "is_it_admin", False))


def _day(value):
    try:
        return datetime.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def audit_logs(request):
    if not _is_admin(request.user):
        return Response({"detail": "Only the IT Admin can see the audit logs."}, status=status.HTTP_403_FORBIDDEN)
    q = request.query_params
    qs = AuditLog.objects.all()
    if q.get("user") == "system":
        qs = qs.filter(user__isnull=True)
    elif q.get("user"):
        try:
            qs = qs.filter(user_id=int(q["user"]))
        except ValueError:
            return Response({"detail": "user must be a number."}, status=status.HTTP_400_BAD_REQUEST)
    if q.get("action"):
        if q["action"] not in dict(AuditLog.ACTIONS):
            return Response({"detail": "Unknown action."}, status=status.HTTP_400_BAD_REQUEST)
        qs = qs.filter(action=q["action"])
    d1, d2 = _day(q.get("date_from")), _day(q.get("date_to"))
    if (q.get("date_from") and not d1) or (q.get("date_to") and not d2):
        return Response({"detail": "Dates must look like 2026-11-06."}, status=status.HTTP_400_BAD_REQUEST)
    if d1:
        qs = qs.filter(timestamp__date__gte=d1)
    if d2:
        qs = qs.filter(timestamp__date__lte=d2)
    if q.get("entity"):
        qs = qs.filter(entity=q["entity"])
    if q.get("q"):
        from django.db.models import Q
        text = q["q"].strip()[:100]
        qs = qs.filter(Q(summary__icontains=text) | Q(entity__icontains=text) | Q(entity_id__icontains=text) | Q(user_label__icontains=text))
    try:
        page = max(1, int(q.get("page") or 1))
    except ValueError:
        page = 1
    total = qs.count()
    rows = qs[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
    users = [{"id": uid, "label": label or f"User #{uid}"} for uid, label in
             AuditLog.objects.filter(user__isnull=False).order_by("user_label").values_list("user_id", "user_label").distinct()]
    seen, user_list = set(), []
    for u in users:                         # one entry per account (the newest name is enough for the filter)
        if u["id"] not in seen:
            seen.add(u["id"])
            user_list.append(u)
    return Response({
        "count": total, "page": page, "page_size": PAGE_SIZE, "pages": max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
        "results": [{"id": r.id, "timestamp": r.timestamp.isoformat(), "user_id": r.user_id, "user": r.user_label or "System",
                     "action": r.action, "entity": r.entity, "entity_id": r.entity_id, "summary": r.summary,
                     "old_values": r.old_values, "new_values": r.new_values, "ip_address": r.ip_address} for r in rows],
        "users": user_list, "actions": [{"value": k, "label": v} for k, v in AuditLog.ACTIONS],
        "entities": sorted(set(AuditLog.objects.values_list("entity", flat=True).distinct())),
    })
