from unittest import result
from src.db.models import Requests
from src.db.db import exec_db


def save_request(db, text, intent, chosen_schema, result, member_id):
    """
    INSERT INTO public.requests
    (id, requester_id, request_text, embedding, created_at, request_type, extracted_filters)
    VALUES(nextval('requests_id_seq'::regclass),'4c13b67d-c098-47a8-9d72-cf72e169c54e', '', ?, now(), '', '');
    """

    # request is constructed

    # inside build_request_payload, before inserting into DB
    extracted_filters = result.model_dump(mode="json")

    assert isinstance(extracted_filters, dict)

    # extract summary from pydentic object if exists
    summary = result.summary if hasattr(result, "summary") else None

    new_request = Requests(
        request_text=text,
        request_type=chosen_schema.__name__,
        extracted_filters=extracted_filters,  # Placeholder for extracted filters)
        requester_id=member_id,
        summary=summary,
        embedding=None,  # Placeholder for embedding
    )

    exec_db(new_request)

    return True
