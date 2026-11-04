"""
Room ownership rules, shared by the class scheduler, the exam scheduler, merged minor classes and
manual edits so they all agree:

* A room whose `department` is set is RESERVED for that department: only sections of that
  department's programs may use it. (M-HJ -> IHM; Comp Lab C / D -> Computer Studies.)
* A room reserved for SHS/JHS (Comp Lab B) matches no college department, so no college class uses it.
* A room with no department is shared.
* A department that owns laboratory rooms uses ONLY its own labs for lab subjects.
"""
import re

SHS_JHS = "Senior High / Junior High"


def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip()).casefold()


def may_use(room, dept):
    """True when a section of department `dept` may be placed in `room`."""
    owner = getattr(room, "department", None)
    return (not owner) or norm(owner) == norm(dept)


def owns_labs(rooms, dept):
    return any(getattr(r, "room_type", "") == "lab" and getattr(r, "department", None) and norm(r.department) == norm(dept)
               for r in rooms)


def floor_of(room):
    """Floor from the room number ("307" / "D-307" / "307D" -> 3); None when it cannot be read."""
    for src in (getattr(room, "room_number", ""), getattr(room, "name", "")):
        m = re.search(r"(\d)\d{2}", str(src or ""))
        if m:
            return int(m.group(1))
    return None


def is_owned_lab(room):
    """A laboratory that belongs to a department (e.g. Comp Lab C / D): kept for lab classes only."""
    return getattr(room, "room_type", "") == "lab" and bool(getattr(room, "department", None))


def is_library(room):
    """The Library is in the class-program room list (it was used for a few classes) but is not a classroom: kept as a last resort."""
    return "library" in ((getattr(room, "name", "") or "") + " " + (getattr(room, "label", "") or "")).lower()


def allowed_rooms(rooms, dept, lab_subject=False, major=False):
    """Rooms (from `rooms`) this department may use; for lab subjects, its own labs when it has any.
    A GEN ED lecture never takes a department's laboratory when any other room is available; a MAJOR
    lecture of the department that owns the lab (Computer Studies in Comp Lab C / D) may."""
    rooms = list(rooms)
    ok = [r for r in rooms if may_use(r, dept)]
    if not lab_subject and not major:
        lectures = [r for r in ok if not is_owned_lab(r)]
        if lectures:
            ok = lectures
    if not lab_subject:
        # a lecture goes to a real classroom; the Library is used only when no other room is allowed at all
        classrooms = [r for r in ok if not is_library(r)]
        if classrooms:
            ok = classrooms
    if lab_subject:
        own = [r for r in ok if getattr(r, "room_type", "") == "lab" and getattr(r, "department", None)]
        if own:
            return own
    return ok


def is_computer_studies(dept):
    return "comput" in (dept or "").lower()


def designated_rooms(rooms, dept):
    """The rooms a department's MAJOR subjects must use, or None when the department has no such hard rule.
    Computer Studies (BSCS, BSIT): Comp Lab C and Comp Lab D (the labs the department owns), for lectures and laboratories alike
    (GTI class program). The generator, the Dean's room choice and Resolve never use an ordinary lecture room for them."""
    if not is_computer_studies(dept):
        return None
    own = [r for r in rooms if is_owned_lab(r) and may_use(r, dept) and norm(r.department) == norm(dept)]
    return own or None


def designated_message(subject, dept, rooms):
    names = ", ".join(sorted(r.name for r in (designated_rooms(rooms, dept) or [])))
    return (f"{subject.code} is a {dept} major subject, so it must use the department's designated rooms ({names}). "
            "Ordinary lecture rooms are not allowed for it. Choose Comp Lab C or Comp Lab D.")


def reserved_message(room, dept):
    return (f"Room {room.name} is reserved for {room.department}; a section of {dept or 'another department'} "
            f"cannot use it.")


# ---------------------------------------------------------------------------------------------------------
# Dean's per-subject room assignments (rooms.SubjectRoomAssignment), made visible to the scheduler for one
# generation run through a context variable so the many build_domain / ordering call sites stay unchanged.
# ---------------------------------------------------------------------------------------------------------
from contextvars import ContextVar

_ASSIGN = ContextVar("subject_room_assignments", default={})


def load_assignments(subject_ids=None):
    """{subject_id: {"preferred": room_id|None, "alts": [room_id, ...], "fixed": bool}}"""
    from .models import SubjectRoomAssignment
    qs = SubjectRoomAssignment.objects.prefetch_related("alternative_rooms")
    if subject_ids is not None:
        qs = qs.filter(subject_id__in=list(subject_ids))
    return {a.subject_id: {"preferred": a.preferred_room_id,
                           "alts": [r.id for r in a.alternative_rooms.all()],
                           "fixed": bool(a.is_fixed and a.preferred_room_id)} for a in qs}


def use_assignments(mapping):
    return _ASSIGN.set(mapping or {})


def release_assignments(token):
    _ASSIGN.reset(token)


# Start / end time the user picked for a subject in the curriculum preview: {subject_id: (start_minutes, end_minutes)}.
# Hard rule for that subject only: every period of its class blocks must lie inside the window.
_TIMES = ContextVar("subject_time_windows", default={})


def use_time_windows(mapping):
    return _TIMES.set(mapping or {})


def release_time_windows(token):
    _TIMES.reset(token)


def time_window_for(subject_id):
    return _TIMES.get().get(subject_id)


def assignment_for(subject_id):
    return _ASSIGN.get().get(subject_id)


# Professor the Dean picked for a subject in the Generate preview (this run only): {subject_id: faculty_id}.
# Like a fixed room it only narrows that subject's choices: the engine may use this teacher and nobody else for it.
_TEACHERS = ContextVar("subject_teacher_choices", default={})


def use_teacher_choices(mapping):
    return _TEACHERS.set(mapping or {})


def release_teacher_choices(token):
    _TEACHERS.reset(token)


def teacher_choice_for(subject_id):
    return _TEACHERS.get().get(subject_id)


# Shared (merged) minor classes: while the batch minor generator runs, the host section of a shared class is sized for the
# WHOLE group, so the room it gets can seat the sections that will join it. {(section_id, subject_id): total students}
_GROUP = ContextVar("shared_class_sizes", default={})


def use_group_sizes(mapping):
    return _GROUP.set(mapping)


def release_group_sizes(token):
    _GROUP.reset(token)


# Time a shared class must avoid because a member section (another program) already has a class then:
# {(host_section_id, subject_id): [(day index, start min, end min), ...]}
_SHARE_BUSY = ContextVar("shared_class_busy", default={})


def use_share_busy(mapping):
    return _SHARE_BUSY.set(mapping or {})


def release_share_busy(token):
    _SHARE_BUSY.reset(token)


def share_busy_for(section, subject):
    return _SHARE_BUSY.get().get((section.id, subject.id), ())


def current_group_sizes():
    return dict(_GROUP.get())


def effective_size(section, subject):
    own = getattr(section, "student_count", 0) or 0
    return max(own, _GROUP.get().get((section.id, subject.id), 0))


def fits_size(room, section):
    size = getattr(section, "student_count", 0) or 0
    cap = getattr(room, "capacity", 0) or 0
    return not size or not cap or cap >= size


def assign_rank(room, section, subject):
    """0 = the Dean's preferred room, 1 = one of the alternatives, 2 = anything else (or a room too small)."""
    a = assignment_for(subject.id)
    if not a or not fits_size(room, section):
        return 2
    if room.id == a["preferred"]:
        return 0
    return 1 if room.id in a["alts"] else 2


def room_kind_message(subject, room):
    """A lecture class may not be put into a department's laboratory by hand either."""
    if (room is not None and getattr(subject, "lab_units", 0) == 0 and is_owned_lab(room)
            and getattr(subject, "classification", "") == "minor"):
        return f"{subject.title} is a Gen Ed lecture class: use a lecture room instead of the laboratory {room.name}."
    return None


def fixed_room_message(subject, room):
    """If the Dean FIXED this subject to a room, picking any other room is refused; returns the message or None."""
    from .models import SubjectRoomAssignment
    a = SubjectRoomAssignment.objects.filter(subject=subject, is_fixed=True).select_related("preferred_room").first()
    if a is None or a.preferred_room_id is None or room is None or a.preferred_room_id == room.id:
        return None
    return (f"{subject.title} is fixed to room {a.preferred_room.name}. "
            f"Change or untick 'Fixed' in the Room assignments (Schedules tab) first to use {room.name}.")


# ----------------------------------------------------------------------------- finding / naming rooms
def room_key(text):
    """'D-307' / '307D' / 'Comp Lab C' -> 'D307' / '307D' / 'COMPLABC' (letters and digits only, upper case)."""
    return re.sub(r"[^A-Z0-9]", "", str(text or "").upper())


def room_code(room):
    """The short code the school uses for a numbered room: '307D', '301M', 'A-101'. '' for a named room
    (Kitchen 1, Anatomy Lab ...) whose name already says everything."""
    b = getattr(room, "building", "") or ""
    num = str(getattr(room, "room_number", "") or "").strip()
    if b and num.isdigit():
        return f"A-{num}" if b == "A" else f"{num}{b}"
    return ""


def room_text(room):
    """Name shown in dropdowns: 'Comp Lab D (309D)' for a labelled numbered room, '309D' for a plain one,
    'Kitchen 1' for a named room."""
    code = room_code(room)
    lab = (getattr(room, "label", "") or "").strip()
    if lab.lower() in ("demo room", "sample room"):
        lab = ""
    if not code:
        return lab or str(getattr(room, "name", "") or "")
    return f"{lab} ({code})" if lab and room_key(lab) != room_key(code) else code


# ----------------------------------------------------------------------------- department HOME rooms (GTI)
import time as _time

_HOME_CACHE = {"at": 0.0, "by_dept": {}}


def home_ids(dept):
    """Ids of the rooms that are `dept`'s home rooms (GTI class program), cached for a few seconds."""
    if _time.time() - _HOME_CACHE["at"] > 15:
        from .models import DepartmentRoom
        by = {}
        for d, rid in DepartmentRoom.objects.values_list("department", "room_id"):
            by.setdefault(norm(d), []).append(rid)
        _HOME_CACHE.update(at=_time.time(), by_dept=by)
    return _HOME_CACHE["by_dept"].get(norm(dept), [])


def clear_home_cache():
    _HOME_CACHE["at"] = 0.0


def home_rank(room, dept):
    """0 = one of the department's home rooms (by order), 1 = not a home room (or the department has none)."""
    ids = home_ids(dept)
    if not ids:
        return 1
    try:
        return 0 if room.id in ids else 1
    except Exception:
        return 1
