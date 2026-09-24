"""Exercise the conversation query and its keyset cursor against a real database.

The point of the cursor is behavior a mocked Session cannot show: whether rows
sharing a ``created_at`` to the microsecond are all returned. They arise
naturally, because a fan-out writes its copies inside one transaction and
``func.now()`` is transaction time, so the siblings share a timestamp exactly.
A cursor on ``created_at`` alone would step over all but one of them and never
come back.

Writes into a rolled-back transaction, so it leaves no rows behind:

    ./.venv/bin/python scripts/verify_conversation_cursor.py
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv("../.env")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from src.core.managers.message_manager import MessageManager  # noqa: E402
from src.domain.message_role import MessageKind  # noqa: E402
from src.models import Group, Member, Message  # noqa: E402


def main() -> int:
    engine = create_engine(os.environ["DATABASE_URL"])
    manager = MessageManager()
    failures = []

    with Session(engine) as db:
        group = db.query(Group).first()
        member = db.query(Member).first()
        other = db.query(Member).filter(Member.id != getattr(member, "id", None)).first()
        if group is None or member is None or other is None:
            print("Needs a group and two members in this database; nothing to verify.")
            return 0

        # Everything below happens inside a transaction that is rolled back.
        # A verification script must not leave test messages in a real group.
        inbound = manager.create_inbound(
            db,
            group_id=group.id,
            member_id=member.id,
            kind=MessageKind.ORIGINAL_REQUEST,
            from_phone_number=member.phone_number,
            to_phone_number="+15550000000",
            body="[verify] does anyone have an axe?",
        )
        # Three outbound rows in this same transaction, so all four share one
        # created_at exactly. This is the case the composite cursor exists for.
        siblings = [
            manager.create_outbound(
                db,
                group_id=group.id,
                member_id=member.id,
                kind=MessageKind.FANOUT_COPY,
                from_phone_number="+15550000000",
                to_phone_number=member.phone_number,
                body=f"[verify] copy {n}",
            )
            for n in range(3)
        ]
        # A message about a different member must not appear in this
        # conversation, even though it is in the same group.
        manager.create_outbound(
            db,
            group_id=group.id,
            member_id=other.id,
            kind=MessageKind.FANOUT_COPY,
            from_phone_number="+15550000000",
            to_phone_number=other.phone_number,
            body="[verify] somebody else's copy",
        )
        db.flush()

        mine = {inbound.id, *(s.id for s in siblings)}
        stamps = {m.created_at for m in (inbound, *siblings)}
        print(f"four rows written across {len(stamps)} distinct created_at value(s)")

        # 1. The conversation is scoped to one member and returned oldest first.
        page = manager.list_conversation(
            db, group_id=group.id, member_id=member.id
        )
        ids = [m.id for m in page]
        if not mine.issubset(set(ids)):
            failures.append("full load omitted rows from this conversation")
        if any(m.member_id != member.id for m in page):
            failures.append("full load leaked another member's messages")
        stamps_in_order = [m.created_at for m in page]
        if stamps_in_order != sorted(stamps_in_order):
            failures.append("full load was not oldest-first")
        print(f"full load returned {len(page)} messages for this pair")

        # 2. Walking the cursor one row at a time yields every remaining row
        #    exactly once and in the same order as the full load.
        #
        #    This is the property that matters, and the one a created_at-only
        #    cursor breaks. Note it is *not* "paging from the oldest row returns
        #    all the others": ``id`` is a random UUID, so among rows tied on
        #    created_at the sort position of any given row is arbitrary, and rows
        #    sorting before the cursor were already delivered in an earlier page.
        walked = []
        step = page[0]
        while True:
            nxt = manager.list_conversation(
                db,
                group_id=group.id,
                member_id=member.id,
                after_created_at=step.created_at,
                after_id=step.id,
                limit=1,
            )
            if not nxt:
                break
            walked.append(nxt[0])
            step = nxt[0]

        if [m.id for m in walked] != [m.id for m in page[1:]]:
            failures.append(
                "walking the cursor did not reproduce the full load exactly"
            )
        print(f"walking one row at a time visited {len(walked)} of {len(page) - 1}")

        # 3. What the cursor's second half is for: with created_at alone, the
        #    rows tied with the starting row are unreachable forever.
        would_skip = [
            m for m in page[1:] if m.created_at == page[0].created_at
        ]
        print(
            f"a created_at-only cursor would strand {len(would_skip)} tied row(s)"
        )

        # 4. Paging from the last row returns nothing. This is the call the
        #    simulator's poll actually makes, every three seconds.
        last = page[-1]
        tail = manager.list_conversation(
            db,
            group_id=group.id,
            member_id=member.id,
            after_created_at=last.created_at,
            after_id=last.id,
        )
        if tail:
            failures.append(f"cursor at the newest row still returned {len(tail)}")
        print(f"paging from the newest row returned {len(tail)} message(s)")

        db.rollback()
        remaining = (
            db.query(Message)
            .filter(Message.body.like("[verify]%"))
            .count()
        )
        if remaining:
            failures.append(f"{remaining} verification row(s) survived the rollback")

    for failure in failures:
        print(f"FAIL: {failure}")
    print("OK" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
