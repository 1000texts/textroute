"""Read the conversation between one member's handset and one group's number.

Exists for the SMS simulator, which stands in for a real phone in development.
Before this, the simulator invented its own history in browser memory, so a
fan-out copy or a moderator's reply -- the very things worth testing -- never
appeared on the fake handset. Reading the ``messages`` table instead makes the
simulator a view of what actually happened.

Nothing here composes or decorates text. An outbound row already reads
"Naruto: ..." because that is the SMS that was sent, prefixed on the way out by
``src.domain.outbound_text``; the handset shows the stored body verbatim, which
is the only way it can be trusted to represent a real phone.

Read-only, so nothing here commits.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from src.core.managers.membership_manager import MembershipManager
from src.core.managers.message_manager import MessageManager
from src.core.managers.phone_number_manager import PhoneNumberManager
from src.models import Message
from src.services.inbound_errors import (
    UnassignedPhoneNumberError,
    UnknownReceivingNumberError,
)


class SimulatorService:
    def __init__(self):
        self.phone_number_manager = PhoneNumberManager()
        self.membership_manager = MembershipManager()
        self.message_manager = MessageManager()

    def load_conversation(
        self,
        db: Session,
        *,
        member_phone_number: str,
        group_phone_number: str,
        after_created_at: datetime | None = None,
        after_id: UUID | None = None,
    ) -> list[Message]:
        """Messages between these two numbers, oldest first.

        The same two errors the inbound webhook raises for an unusable ``to``
        number, so the simulator gets one consistent answer whether it is
        sending or reading.
        """
        # Both managers normalize the number themselves, so a simulator typing
        # "5551234567" resolves the same as "+15551234567".
        phone_number = self.phone_number_manager.find_by_number(
            db,
            group_phone_number,
        )
        if phone_number is None:
            raise UnknownReceivingNumberError(
                f"Unknown TextRoute number: {group_phone_number}"
            )
        if phone_number.group_id is None:
            raise UnassignedPhoneNumberError(
                f"TextRoute number is not assigned to a group: {group_phone_number}"
            )

        member = self.membership_manager.get_by_phone(db, member_phone_number)
        # Not an error. A number nobody has texted from yet simply has no
        # history, and the simulator should show an empty thread rather than a
        # failure the moment someone types a new From number.
        if member is None:
            return []

        return self.message_manager.list_conversation(
            db,
            group_id=phone_number.group_id,
            member_id=member.id,
            after_created_at=after_created_at,
            after_id=after_id,
        )
