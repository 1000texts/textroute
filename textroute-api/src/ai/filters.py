from src.ai.embedding import get_dense_vector
from src.schemas.schema_config import SCHEMA_CONFIG


def build_vector_query(
    *,
    schema_type: str,
    # Logical schema key (e.g., "announcement", "borrow_request", "service_request")
    user_text: str,
    # Original user query text. Used to generate a dense vector embedding for vector similarity search.
    structured_filters: dict,
    # Structured, schema-aware filters extracted from user input or an LLM.
    # Only fields explicitly allowed by the schema configuration will be applied.
    limit: int = 10,
    # Maximum number of results to return, ordered by vector similarity.
):
    # Retrieve schema-specific configuration (table name, allowed filters, etc.)
    # This enforces schema isolation and prevents cross-table querying.
    config = SCHEMA_CONFIG[schema_type]

    # Target database table for the selected schema
    table = config.table

    # Set of filterable fields explicitly allowed for this schema
    # Acts as a whitelist to prevent invalid filters or SQL injection via field names
    allowed_filters = config.filters

    # Convert Pydantic model → dict
    if hasattr(structured_filters, "model_dump"):
        filters_dict = structured_filters.model_dump(exclude_none=True)
    else:
        filters_dict = structured_filters  # already a dict

    # Accumulates SQL WHERE conditions derived from valid structured filters
    where_clauses = []

    # Dense vector representation of the user query.
    # Must be compatible with the pgvector embedding column.
    query_embedding = get_dense_vector(user_text=user_text)

    # Query parameters for safe, parameterized SQL execution
    params = {
        "embedding": query_embedding,
        "limit": limit,
    }

    # Build structured WHERE conditions using only schema-approved fields
    for key, value in filters_dict.items():
        if key in allowed_filters:
            where_clauses.append(f"{key} = :{key}")
            params[key] = value

    # Build SQL WHERE clauses using only schema-approved, non-null filters
    # '=' affected_areas, audience, available_slots, available_until, rating, priority, rating, related_request_id, return_date, service_type, severity, status, urgency
    # '<' available_until, borrow_date, created_by, due_date, expires_at, rating, related_request_id, return_date, service_type, severity, status, urgency
    # '>' available_from, , borrow_date, created_by, due_date, expires_at, rating, related_request_id, return_date, service_type, severity, status, urgency

    for key, value in filters_dict.items():
        # Skip fields not allowed by the schema or unset values
        if key not in allowed_filters or value is None:
            continue

        # Range filter: item must be available on or before this date
        if key == "available_from":
            where_clauses.append("available_from <= :available_from")
            params[key] = value

        # Range filter: item must be available on or after this date
        elif key == "available_until":
            where_clauses.append("available_until >= :available_until")
            params[key] = value

        # Exact match filter for all other fields
        else:
            where_clauses.append(f"{key} = :{key}")
            params[key] = value

    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)
    else:
        where_sql = ""

    # Final SQL query:
    # - Applies schema-scoped structured filters (if any)
    # - Computes cosine similarity using pgvector (<=>)
    # - Orders results by closest embedding distance
    # - Limits the result set for performance
    sql = f"""
        SELECT
            *,
            1 - (embedding <=> :embedding) AS similarity
        FROM {table}
        {where_sql}
        ORDER BY embedding <=> :embedding
        LIMIT :limit;
    """

    # Return the parameterized SQL query and its bound parameters
    return sql, params
