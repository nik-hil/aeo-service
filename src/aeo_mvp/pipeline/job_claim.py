"""Atomic single-owner job claim (P0-5).

DB row status is the source of truth. Ownership is acquired with a compare-and-swap
``UPDATE … WHERE status IN claimable``, committed before any crawl / provider work.

Crash / stale claim tradeoff
----------------------------
No lease or heartbeat is implemented. If a worker dies after a successful claim
(status ``claimed`` or a later in-flight status that was committed), the job stays
in that status until an operator resets it to ``pending`` (or ``failed`` → reclaim).
Jobs are not auto-unbricked; this avoids false dual-ownership from an aggressive
timeout. Explicit retry API is out of scope for P0-5.

SQLite vs Postgres
------------------
* **Postgres:** ``UPDATE … WHERE status=…`` under READ COMMITTED gives a true
  cross-connection / cross-process CAS (``rowcount == 1`` ⇒ sole owner).
* **SQLite (file URL):** writers are serialized by the DB file lock, so the same
  CAS pattern works across processes that share one file database. This is not a
  distributed lock across *different* database files or replicas.
* **SQLite ``:memory:``:** not shared across processes; do not claim cross-process
  safety for in-memory engines.
* This module does **not** swap the configured engine or add an external lock service.
"""

from __future__ import annotations

import logging
import os
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.orm import Session

from aeo_mvp.db.models import Job, utc_now_iso

logger = logging.getLogger(__name__)

# Ownership marker — durable after claim commit, before expensive pipeline work.
CLAIMED_STATUS = "claimed"

# Statuses from which a worker may atomically take ownership.
CLAIMABLE_STATUSES: frozenset[str] = frozenset({"pending", "failed"})

# In-flight: already owned / executing (second worker must not start).
IN_FLIGHT_STATUSES: frozenset[str] = frozenset(
    {
        CLAIMED_STATUS,
        "crawling",
        "analyzing",
        "scoring",
        "experimenting",
        "synthesizing",
    }
)


class JobClaimConflict(Exception):
    """Raised when this worker did not win the atomic claim.

    Claim conflict is **not** a provider failure — do not transition the job to
    ``failed`` because of this exception.
    """

    def __init__(
        self,
        job_id: str,
        *,
        current_status: str,
        reason: str,
        worker_id: str | None = None,
    ) -> None:
        self.job_id = job_id
        self.current_status = current_status
        self.reason = reason
        self.worker_id = worker_id
        super().__init__(
            f"job {job_id} claim conflict: reason={reason} status={current_status}"
        )


def new_worker_id() -> str:
    """Opaque worker/owner id for logs (not a secret)."""
    return f"pid-{os.getpid()}-{uuid4().hex[:8]}"


def claim_job(
    session: Session,
    job_id: str,
    *,
    worker_id: str | None = None,
    commit: bool = True,
) -> Job:
    """Atomically claim ``job_id`` for exclusive pipeline execution.

    Performs ``UPDATE jobs SET status='claimed' … WHERE id=? AND status IN
    ('pending','failed')``. Success requires ``rowcount == 1``. The claim is
    committed (when ``commit=True``) **before** returning so ownership is durable
    before crawl / provider / optimization work.

    ``failed`` remains claimable so programmatic re-invocation of ``run()`` after a
    provider failure keeps prior semantics (no separate retry API exists).
    ``completed`` is never implicitly re-executed.
    """
    wid = worker_id or new_worker_id()
    now = utc_now_iso()

    result = session.execute(
        update(Job)
        .where(Job.id == job_id, Job.status.in_(tuple(CLAIMABLE_STATUSES)))
        .values(
            status=CLAIMED_STATUS,
            updated_at=now,
            error_message=None,
            completed_at=None,
        )
        .execution_options(synchronize_session=False)
    )
    rowcount = int(result.rowcount or 0)

    if commit:
        session.commit()

    if rowcount == 1:
        job = session.get(Job, job_id)
        if job is None:
            raise ValueError(f"unknown job {job_id}")
        session.refresh(job)
        logger.info(
            "job_claim_success job_id=%s worker_id=%s from_claimable=1 "
            "new_status=%s",
            job_id,
            wid,
            CLAIMED_STATUS,
        )
        return job

    job = session.get(Job, job_id)
    if job is None:
        raise ValueError(f"unknown job {job_id}")

    if job.status == "completed":
        reason = "completed"
    elif job.status in IN_FLIGHT_STATUSES:
        reason = "already_running"
    else:
        reason = "not_claimable"

    logger.info(
        "job_claim_conflict job_id=%s worker_id=%s current_status=%s reason=%s",
        job_id,
        wid,
        job.status,
        reason,
    )
    raise JobClaimConflict(
        job_id,
        current_status=job.status,
        reason=reason,
        worker_id=wid,
    )
