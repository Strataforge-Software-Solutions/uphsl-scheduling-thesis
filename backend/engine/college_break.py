"""The institution-wide college lunch break enforced by every college schedule path."""
from datetime import time


BREAK_START = time(12, 0)
BREAK_END = time(12, 30)


def overlaps(start, end):
    """Whether a time interval overlaps the reserved daily college break."""
    start_min = start.hour * 60 + start.minute if hasattr(start, "hour") else int(start)
    end_min = end.hour * 60 + end.minute if hasattr(end, "hour") else int(end)
    return start_min < BREAK_END.hour * 60 + BREAK_END.minute and end_min > BREAK_START.hour * 60 + BREAK_START.minute


def is_blocked_slot(slot):
    return overlaps(slot.start_time, slot.end_time)


def allowed_slots(slots):
    return [slot for slot in slots if not is_blocked_slot(slot)]


def message():
    return "College classes cannot be scheduled from 12:00 PM to 12:30 PM. Choose a time outside the reserved lunch break."
