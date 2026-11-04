"""Read-only room usage for the Room dropdown of the Generate preview: how many weekly hours each room is still free in a semester.

Week = every time of the college time-slot grid (TimeSlot table), each day's slots merged so overlapping hourly and half-hour slots
count once. Used = the times a room is booked by class schedules of that semester (any status), merged the same way, so a shared
(merged) class -- several sections in one room at one time -- counts once. Free = week - used. Nothing is written."""
from collections import defaultdict


def _mins(t):
    return t.hour * 60 + t.minute


def _merged_minutes(intervals):
    total, end = 0, None
    for a, b in sorted(intervals):
        if end is None or a >= end:
            total += b - a
            end = b
        elif b > end:
            total += b - end
            end = b
    return total


def free_hours(room_ids, semester):
    """{"total": weekly hours of the grid, "free": {room_id: free hours}} (rooms with no class are absent: free = total)."""
    from engine.models import Schedule, TimeSlot

    grid = defaultdict(list)
    for day, a, b in TimeSlot.objects.values_list("day", "start_time", "end_time"):
        grid[day[:3].title()].append((_mins(a), _mins(b)))
    total = sum(_merged_minutes(v) for v in grid.values()) / 60.0
    booked = defaultdict(list)
    for rid, day, a, b in (Schedule.objects.filter(room_id__in=list(room_ids), section__semester=semester)
                           .values_list("room_id", "timeslot__day", "timeslot__start_time", "timeslot__end_time")):
        booked[(rid, day[:3].title())].append((_mins(a), _mins(b)))
    used = defaultdict(float)
    for (rid, _day), iv in booked.items():
        used[rid] += _merged_minutes(iv) / 60.0
    return {"total": round(total, 2), "free": {rid: round(max(total - h, 0.0), 2) for rid, h in used.items()}}
