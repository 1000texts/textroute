from src.db.models import InboundMessage
from src.db.db import exec_db


def save_msg(db, data):
    """
    Endpoint to receive inbound text messages from a provider.
    Expects JSON payload like:
    {
        "from": "+15551234567",
        "to": "+15559876543",
        "body": "Hello from Twilio!"
    }
    """

    # parsing the request
    sender = data.get("from")
    receiver = data.get("to")
    body = data.get("body")

    # inboud message is constructed
    new_msg = InboundMessage(
        sender=sender,
        receiver=receiver,
        message=body,
    )
    exec_db(new_msg)

    return sender, receiver, body
