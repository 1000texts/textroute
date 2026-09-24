"""What an outbound SMS says, and that it is composed exactly once.

A recipient sees only the group's TextRoute number, so the name is part of the
message rather than a display convention. These assert the wording, and that the
provider payload and the stored row are the same string -- a divergence there
would leave the record claiming something else was sent.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from src.domain.message_role import MessageKind
from src.domain.outbound_text import sender_prefix, with_sender
from src.services.messaging_service import MessagingService


def test_a_member_is_named_without_a_role():
    text = with_sender(
        "Can anyone watch my dog this Sunday?",
        sender_name="Naruto",
        kind=MessageKind.FANOUT_COPY,
    )

    assert text == "Naruto: Can anyone watch my dog this Sunday?"


def test_a_moderator_is_marked_as_one():
    """The recipient should know this came from whoever runs the group."""
    text = with_sender(
        "Could you clarify your question?",
        sender_name="Austin",
        kind=MessageKind.MODERATOR_CLARIFICATION,
    )

    assert text == "Austin (Moderator): Could you clarify your question?"


def test_the_kind_may_arrive_as_a_plain_string():
    """``kind`` comes off a database column as often as from the enum, and
    ``Enum.__hash__`` hashes the member name, so a dict keyed by members would
    silently miss the equal string."""
    assert (
        sender_prefix(sender_name="Austin", kind="moderator_clarification")
        == "Austin (Moderator): "
    )
    assert sender_prefix(sender_name="Naruto", kind="fanout_copy") == "Naruto: "


def test_no_name_means_no_prefix():
    """A member with no name on record, or an untraceable author. A bare ": "
    would look like a bug to whoever received it."""
    for name in (None, "", "   "):
        assert (
            with_sender("Hello", sender_name=name, kind=MessageKind.FANOUT_COPY)
            == "Hello"
        )


def test_the_body_is_otherwise_untouched():
    body = "  spaces, punctuation: kept.  \nAnd newlines.  "

    text = with_sender(body, sender_name="Naruto", kind=MessageKind.FANOUT_COPY)

    assert text == f"Naruto: {body}"


def test_the_provider_and_the_stored_row_get_the_same_text():
    """Composed once in the service, so the record cannot claim otherwise."""
    provider = MagicMock()
    provider.send_sms.return_value = "prov_1"
    message_manager = MagicMock()
    service = MessagingService(
        message_manager=message_manager,
        sms_provider=provider,
    )
    group = SimpleNamespace(id=uuid4())
    recipient = SimpleNamespace(id=uuid4(), phone_number="+15552222222")

    service.send_message(
        MagicMock(),
        group=group,
        to_member=recipient,
        from_phone_number="+15559876543",
        body="Can anyone watch my dog this Sunday?",
        sender_name="Naruto",
        kind=MessageKind.FANOUT_COPY,
    )

    expected = "Naruto: Can anyone watch my dog this Sunday?"
    assert provider.send_sms.call_args.kwargs["body"] == expected
    assert message_manager.create_outbound.call_args.kwargs["body"] == expected


def test_an_unnamed_send_stores_the_body_as_given():
    provider = MagicMock()
    provider.send_sms.return_value = "prov_1"
    message_manager = MagicMock()
    service = MessagingService(
        message_manager=message_manager,
        sms_provider=provider,
    )

    service.send_message(
        MagicMock(),
        group=SimpleNamespace(id=uuid4()),
        to_member=SimpleNamespace(id=uuid4(), phone_number="+15552222222"),
        from_phone_number="+15559876543",
        body="Anyone got a ladder?",
        kind=MessageKind.FANOUT_COPY,
    )

    assert provider.send_sms.call_args.kwargs["body"] == "Anyone got a ladder?"
    assert (
        message_manager.create_outbound.call_args.kwargs["body"]
        == "Anyone got a ladder?"
    )
