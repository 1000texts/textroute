from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from src.models.member import Member
from uuid import UUID


def get_or_create_member_id(
    db: Session,
    phone_number: str,
) -> UUID:
    stmt = (
        insert(Member)
        .values(phone_number=phone_number)
        .on_conflict_do_update(
            constraint="members_phone_number_unique",
            set_={
                "phone_number": Member.phone_number,
            },
        )
        .returning(Member.id)
    )

    return db.execute(stmt).scalar_one()


def add(db: Session, member: Member) -> Member:
    db.add(member)
    db.commit()
    db.refresh(member)
    return member
