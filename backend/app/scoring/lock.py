"""Serialises writes to the scoring tables.

The API runs in a single uvicorn worker (see PLAN.md), but sync endpoints are
executed in a thread pool, so a settings PATCH and a snapshot PUT can arrive at
the same time. Both rewrite app.customer_scores/app.service_scores with
DELETE + INSERT, which must not interleave. A re-entrant lock keeps nested calls
(load_snapshot -> recompute) working.
"""

from threading import RLock

RECOMPUTE_LOCK = RLock()
