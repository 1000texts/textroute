from src.ai.extraction import analyze_request_payload
from src.db.db import exec_db
from src.db.models import InboundMessage
from src.services.onboarding import (
    capture_info,
    get_consent,
    get_moderator_apporval,
    get_or_create_member_id,
)
from src.services.requests import save_request


def save_msg(db, sender, receiver, body):
    new_msg = InboundMessage(
        sender=sender,
        receiver=receiver,
        message=body,
    )
    exec_db(new_msg)

    return sender, receiver, body


def handle_inbound_message(db, sender, receiver, body):
    # save the inbound message
    sender, receiver, text = save_msg(db, sender, receiver, body)

    # Init steps:
    # get or create member_id
    member_id, is_need_info, is_need_consent, is_need_approval = (
        get_or_create_member_id(db, sender, receiver)
    )

    # capture info
    if is_need_info:
        capture_info(member_id)

    # ask for consent,
    if is_need_consent:
        get_consent(member_id)

    # moderator apporval,
    if is_need_approval:
        get_moderator_apporval(member_id)

    # open/continue conversation,
    conversation_history = retrieve_conversation(member_id)  # pyright: ignore[reportUndefinedVariable]

    # identify intent and build schema-aware payload
    intent, chosen_schema, result = analyze_request_payload(text)
    print(f"Request type: {result}")

    # save request to database
    save_request(db, text, intent, chosen_schema, result, member_id)

    # build query based on intent and schema-aware payload
    # query, params = build_vector_query(
    #     schema_type=intent,
    #     user_text=text,
    #     structured_filters=result,
    #     limit=10,
    # )

    # result = execute_query(query, params)

    return result, "Intent: " + intent, "Schema: " + chosen_schema.__name__
