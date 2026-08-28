from uuid import UUID

from sqlalchemy.orm import Session

from src.models import Group


class GroupManager:
    """Persistence helpers for groups. Flush only — callers own commit."""

    def create_group(
        self,
        db: Session,
        name: str,
        description: str | None,
    ) -> Group:
        group = Group(
            name=name,
            description=description,
            status="active",
        )
        db.add(group)
        db.flush()
        return group

    def update_group(
        self,
        db: Session,
        group: Group,
        name: str,
        description: str | None,
    ) -> Group:
        group.name = name
        group.description = description
        db.add(group)
        db.flush()
        return group

    def get_group(
        self,
        db: Session,
        group_id: UUID,
    ) -> Group | None:
        return db.query(Group).filter(Group.id == group_id).first()
