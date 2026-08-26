"""Domain errors for inbound SMS handling."""


class InboundMessageError(Exception):
    """Base class for inbound workflow failures."""


class UnknownReceivingNumberError(InboundMessageError):
    """To number is not in phone_numbers."""


class UnassignedPhoneNumberError(InboundMessageError):
    """PhoneNumber exists but has no group_id / is not assigned."""


class UnknownSenderError(InboundMessageError):
    """From number is not a known Member."""


class SenderNotInGroupError(InboundMessageError):
    """Member exists but is not an active member of the receiving group."""


class DuplicateInboundMessageError(InboundMessageError):
    """Provider message id was already recorded."""

    def __init__(self, message_id: str):
        self.message_id = message_id
        super().__init__(f"Duplicate inbound message: {message_id}")
