from sqlalchemy.orm import Session

from src.models import Group


class GroupManager:

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


# def update_group(...):
#     ...

# def get_group(...):
#     ...

# def add_moderator(...):
#     ...

# def get_groups_for_moderator(...):
#     ...

# def deactivate_group(...):
#     ...
