"""
One generation at a time.

Generating a schedule is a long database transaction that inserts rows guarded by unique constraints
(no_section_double_booking, no_room_double_booking, ...). On PostgreSQL an INSERT that hits a unique index entry written by
ANOTHER transaction that has not committed yet WAITS for that transaction. When a second run starts while the first is
still going (a double click, a page refresh -- the server keeps running the abandoned request -- or two staff generating
together), the second run sat waiting until Supabase cancelled it with
    "canceling statement due to statement timeout ... while inserting index tuple ... no_section_double_booking".
That is not a scheduling-rule failure: it is two generations colliding. So every generation first takes a transaction-level
advisory lock (released automatically on commit/rollback/disconnect) and, if somebody else holds it, answers immediately with
a clear message instead of queuing behind them. A lock_timeout also makes any other blocked wait fail fast with a readable error.
"""
from django.db import OperationalError, connection

BUSY = ("Another schedule generation is still running. Wait for it to finish (it can take a minute), then try again. "
        "Do not click Generate twice or refresh while it runs.")
STUCK = ("The database is still busy with an earlier generation that never finished, so this one was cancelled instead of "
         "waiting. Wait a minute and try again; if it keeps happening, ask the IT admin to run this in the Supabase SQL editor: "
         "select pg_terminate_backend(pid) from pg_stat_activity where state = 'idle in transaction' "
         "and datname = current_database() and pid <> pg_backend_pid();")


def try_lock(name, wait_seconds=20):
    """Call inside transaction.atomic(). True when this transaction now owns the generation lock for `name`."""
    if connection.vendor != "postgresql":
        return True
    with connection.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_xact_lock(hashtext(%s))", [f"uphsl-generate-{name}"])
        got = cur.fetchone()[0]
        if got:
            cur.execute(f"SET LOCAL lock_timeout = '{int(wait_seconds)}s'")
    return bool(got)


def explain(exc):
    """Readable text for a database wait/timeout error, or None when the error is something else."""
    t = str(exc).lower()
    if isinstance(exc, OperationalError) and ("lock timeout" in t or "statement timeout" in t or "deadlock" in t):
        return STUCK
    return None


def require(name):
    """try_lock that raises a 409 API error (for views that already run inside transaction.atomic)."""
    from rest_framework.exceptions import APIException
    if not try_lock(name):
        class Busy(APIException):
            status_code = 409
            default_detail = BUSY
        raise Busy()
