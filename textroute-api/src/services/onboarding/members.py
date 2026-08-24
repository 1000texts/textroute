from src.config.config import Config  # Sessions and ORM base
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from src.db.models import Member
from uuid import UUID


def get_or_create_member_id(
    # If (sender, receiver) does not exist → INSERT → UUID generated
    # If it does exist → conflict → UPDATE does nothing
    # RETURNING member_id works in both cases
    db: Session,
    sender: str,
    receiver: str,
) -> UUID:
    stmt = (
        insert(Member)
        .values(sender=sender, receiver=receiver)
        .on_conflict_do_update(
            constraint="members_unique_1",  # sender + receiver
            set_={
                # no-op update, required for RETURNING
                "sender": Member.sender
            },
        )
        .returning(
            Member.member_id,
            Member.is_need_info,
            Member.is_need_consent,
            Member.is_need_approval,
        )
    )

    row = db.execute(stmt).one()
    return row.member_id, row.is_need_info, row.is_need_consent, row.is_need_approval

def add(member):

    db.add(member)
    db.commit()
    db.refresh(member)
    return member
