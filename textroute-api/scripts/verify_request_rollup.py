"""Exercise the request rollup and lifecycle sweep against a real database.

The rollup leans on Postgres-specific SQL (``bool_or``, ``COUNT(DISTINCT CASE
...)``) that a mocked Session cannot check, the participant rule is only
meaningful against real rows, and the sweep's ``or_``/``and_`` over a nullable
``expires_at`` is likewise untestable with mocks. Read-only: it reports what a
sweep would close without closing anything. Run it after applying the migration:

    ./.venv/bin/python scripts/verify_request_rollup.py
"""

import os
import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

load_dotenv("../.env")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, event, func  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from src.config.config import Config  # noqa: E402
from src.core.managers.request_manager import RequestManager  # noqa: E402
from src.domain.message_role import MessageKind  # noqa: E402
from src.models import Message, Requests  # noqa: E402
from src.services.request_service import RequestService  # noqa: E402


def main() -> int:
    engine = create_engine(os.environ["DATABASE_URL"])
    manager = RequestManager()
    failures = []

    with Session(engine) as db:
        requests = db.query(Requests).order_by(Requests.id).all()
        if not requests:
            print("No requests in this database; nothing to verify.")
            return 0

        request_ids = [r.id for r in requests]

        # 1. The rollup runs, and costs one statement for the whole page.
        statements = []

        def record(conn, cursor, statement, *rest):
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", record)
        try:
            rollups = manager.summarize_activity(db, request_ids=request_ids)
        finally:
            event.remove(engine, "before_cursor_execute", record)
        print(f"rollup returned {len(rollups)} of {len(request_ids)} requests")
        if len(statements) != 1:
            failures.append(f"expected 1 rollup statement, saw {len(statements)}")

        # 2. Participants match a hand-counted member-side set.
        for request in requests:
            messages = (
                db.query(Message).filter(Message.request_id == request.id).all()
            )
            expected = {
                m.member_id
                for m in messages
                if m.member_id is not None
                and m.kind
                in {
                    MessageKind.ORIGINAL_REQUEST.value,
                    MessageKind.FANOUT_COPY.value,
                    MessageKind.MEMBER_REPLY.value,
                    MessageKind.CONFIRMATION.value,
                }
            }
            rollup = rollups.get(request.id, {})
            actual = rollup.get("participant_count", 0)
            moderator_rows = [
                m
                for m in messages
                if m.kind == MessageKind.MODERATOR_CLARIFICATION.value
            ]
            print(
                f"request {request.id}: participants={actual} "
                f"(expected {len(expected)}), messages="
                f"{rollup.get('message_count', 0)}/{len(messages)}, "
                f"moderator_messages={len(moderator_rows)}, "
                f"needs_review={rollup.get('needs_review', False)}"
            )
            if actual != len(expected):
                failures.append(
                    f"request {request.id}: participants {actual} != {len(expected)}"
                )
            if rollup.get("message_count", 0) != len(messages):
                failures.append(f"request {request.id}: message_count mismatch")

        # 3. The serialized summary carries every field the UI reads.
        service = RequestService()
        summaries = service.list_requests(db, requests[0].group_id)
        required = {
            "confidence",
            "participant_count",
            "message_count",
            "last_activity_at",
            "needs_review",
        }
        for summary in summaries[:1]:
            missing = required - set(summary)
            print(f"summary fields present: {sorted(required - missing)}")
            if missing:
                failures.append(f"summary missing {sorted(missing)}")

        # 4. The thread exposes the routing-operation key the UI groups by.
        detail = service.get_request(
            db, requests[0].id, group_id=requests[0].group_id
        )
        copies = [
            m
            for m in detail["messages"]
            if m["kind"] == MessageKind.FANOUT_COPY.value
        ]
        operations = {c["parent_message_id"] for c in copies}
        print(
            f"request {requests[0].id}: {len(copies)} fan-out copies across "
            f"{len(operations)} routing operation(s)"
        )
        if copies and None in operations:
            failures.append("a fan-out copy has no parent to group it by")

        # 5. last_activity_at is a real timestamp on every request, and agrees
        # with the message history. The backfill is the only thing that can make
        # this true for rows that predate the column, so a mismatch here means
        # the migration did not run or ran before some messages existed.
        for request in requests:
            newest = (
                db.query(func.max(Message.created_at))
                .filter(Message.request_id == request.id)
                .scalar()
            )
            if request.last_activity_at is None:
                failures.append(f"request {request.id}: last_activity_at is NULL")
                continue
            # Not equality: the column is bumped per insert, so a request whose
            # messages were all deleted legitimately keeps a later timestamp.
            if newest is not None and request.last_activity_at < newest:
                failures.append(
                    f"request {request.id}: last_activity_at "
                    f"{request.last_activity_at} predates its newest message "
                    f"{newest}"
                )

        # 6. The sweep query runs. Its or_/and_ over a nullable expires_at plus a
        # NOT NULL last_activity_at is exactly what a mocked Session cannot
        # check. Called with a cutoff far in the past so it selects nothing and
        # stays safe to run against production data.
        now = datetime.now(timezone.utc)
        candidates = manager.list_open_needing_close(
            db,
            now=now - timedelta(days=3650),
            inactive_before=now - timedelta(days=3650),
        )
        print(f"sweep query executed; {len(candidates)} request(s) match a 10-year cutoff")
        if candidates:
            failures.append(
                "the sweep matched requests against a 10-year-old cutoff, "
                "which means the bounds are inverted"
            )

        # What a real sweep would close right now, reported without closing it.
        due = manager.list_open_needing_close(
            db,
            now=now,
            inactive_before=now - Config.REQUEST_INACTIVITY_AFTER,
        )
        for request in due:
            reason = RequestService._close_reason(request, now=now)
            print(f"request {request.id}: due to close, reason={reason}")

    if failures:
        print("\nFAILURES:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
