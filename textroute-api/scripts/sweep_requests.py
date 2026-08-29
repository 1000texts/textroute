"""Advance the request lifecycle: close the ones that went quiet or ran out.

This is the half of the lifecycle that nothing else performs. Requests are opened
by inbound SMS and closed by a moderator, but a request that simply stops being
talked about has no actor to close it -- and while it stays open, the next
unrelated message from any of its members is threaded into it as a reply. Without
this script on a schedule, ``last_activity_at`` is maintained and never read.

Run it from cron; see DEPLOY.md. Safe to run when there is nothing to do, and
safe to overlap with itself: each request is closed inside one transaction and a
second runner simply finds fewer to close.

    docker compose -f docker-compose.prod.yml exec -T textroute \
        python scripts/sweep_requests.py

Locally:

    ./.venv/bin/python scripts/sweep_requests.py
"""

import logging
import os
import sys

# Present for a local run outside the container, where DATABASE_URL lives in the
# repo's .env. In the container the environment is already populated by
# env_file, and python-dotenv leaves existing variables alone.
from dotenv import load_dotenv

API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(os.path.dirname(API_DIR), ".env"))
sys.path.insert(0, API_DIR)

from src.config.config import Config  # noqa: E402
from src.db.db import SessionLocal  # noqa: E402
from src.services.request_service import RequestService  # noqa: E402

# stdout, so cron's redirect captures it in the same log as everything else.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("sweep_requests")


def main() -> int:
    hours = Config.REQUEST_INACTIVITY_AFTER.total_seconds() / 3600
    ceiling = Config.REQUEST_EXPIRES_AFTER.total_seconds() / 3600
    logger.info(
        "sweep_starting inactivity_after=%gh maximum_lifetime=%gh", hours, ceiling
    )

    db = SessionLocal()
    try:
        closed = RequestService().sweep_expired(db)
    except Exception:
        # Cron mails a non-zero exit, which is the only notification this has.
        logger.exception("sweep_failed")
        db.rollback()
        return 1
    finally:
        db.close()

    logger.info("sweep_finished closed=%d", closed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
