# src/schemas/registry.py

from src.schemas.intent.service import ServiceRequest
from src.schemas.intent.borrow import BorrowRequest
from src.schemas.intent.announcement import AnnouncementRequest
from src.schemas.intent.general import GeneralRequest
from src.schemas.intent.offer_service import OfferService
from src.schemas.intent.status_update import StatusUpdate
from src.schemas.intent.warning import Warning
from src.schemas.intent.complaint import Complaint
from src.schemas.intent.feedback import Feedback
from src.schemas.intent.poll import Poll

SCHEMA_REGISTRY = {
    "ServiceRequest": ServiceRequest,
    "BorrowRequest": BorrowRequest,
    "AnnouncementRequest": AnnouncementRequest,
    "GeneralRequest": GeneralRequest,
    "OfferService": OfferService,
    "StatusUpdate": StatusUpdate,
    "Warning": Warning,
    "Complaint": Complaint,
    "Feedback": Feedback,
    "Poll": Poll,
}
