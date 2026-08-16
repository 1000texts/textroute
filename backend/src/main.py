from fastapi import FastAPI, Request, Depends
from sqlalchemy import null
from sqlalchemy.orm import Session
from src.core.embedding import get_dense_vector
from src.core.filters import build_vector_query
from src.service.inbound import save_msg
from src.core.langchain import analyze_request_payload
from src.core.requests import save_request
from src.core.members import get_or_create_member_id
from src.db.db import execute_query, get_db
from fastapi.middleware.cors import CORSMiddleware
from src.core.approval import get_moderator_apporval
from src.core.consent import get_consent
from src.core.capture import capture_info

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "Hello FastAPI!"}


@app.post("/webhook/inbound")
async def inbound_webhook(request: Request, db: Session = Depends(get_db)):

    # read request
    data = await request.json()

    # save the inbound message
    sender, receiver, text = save_msg(db, data)

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
    conversation_history = retrieve_conversation(member_id)

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
