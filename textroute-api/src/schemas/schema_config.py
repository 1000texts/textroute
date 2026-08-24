from dataclasses import dataclass
from typing import Set


@dataclass
class SchemaConfig:
    table: str
    search_table: str
    filters: Set[str]
    text_field: str


SCHEMA_CONFIG = {
    "request_service": SchemaConfig(
        table="service_requests",
        search_table="members_service_offerings",
        filters={"service_type", "priority", "due_date", "created_by"},
        text_field="description",
    ),
    "request_borrow": SchemaConfig(
        table="request_borrows",
        search_table="members_possessions",
        filters={"item_name", "borrow_date", "return_date", "created_by"},
        text_field="purpose",
    ),
    "announcement": SchemaConfig(
        table="announcements",
        search_table="members_announcements",
        filters={"audience", "expires_at", "created_by", "genre"},
        text_field="description",
    ),
    "general": SchemaConfig(
        table="general_requests",
        search_table="members_general_requests",
        filters={"created_by", "genre"},
        text_field="description",
    ),
    "offer_service": SchemaConfig(
        table="service_offers",
        search_table="members_service_offers",
        filters={"service_type", "available_slots", "created_by"},
        text_field="description",
    ),
    "status_update": SchemaConfig(
        table="status_updates",
        search_table="members_status_updates",
        filters={"status", "related_request_id", "created_by"},
        text_field="description",
    ),
    "warning": SchemaConfig(
        table="warnings",
        search_table="members_warnings",
        filters={"severity", "affected_areas", "created_by"},
        text_field="description",
    ),
    "complaint": SchemaConfig(
        table="complaints",
        search_table="members_complaints",
        filters={"urgency", "created_by"},
        text_field="description",
    ),
    "feedback": SchemaConfig(
        table="feedback",
        search_table="members_feedback",
        filters={"feedback_type", "rating", "created_by"},
        text_field="description",
    ),
    "poll": SchemaConfig(
        table="polls",
        search_table="members_polls",
        filters={"expires_at", "created_by"},
        text_field="question",
    ),
}
