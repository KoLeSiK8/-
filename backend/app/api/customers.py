from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import text

from ..auth.deps import require_user

router = APIRouter(dependencies=[Depends(require_user)])
SORT_COLUMNS = {
    "id": "accounts.id",
    "email": "accounts.email",
    "balance": "accounts.balance",
    "total_replenished": 'accounts."totalReplenished"',
    "score": "customer_scores.score",
    "expected_loss": "customer_scores.expected_loss_cents",
}
LEVELS = {"low", "medium", "high", "churned", "no_data"}


@router.get("", summary="Список клиентов с оценкой риска")
def list_customers(
    request: Request,
    level: list[str] | None = Query(default=None),
    q: str | None = None,
    sort_by: Literal[
        "id", "email", "balance", "total_replenished", "score", "expected_loss"
    ] = "id",
    order: Literal["asc", "desc"] = "asc",
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> dict:
    if level and any(item not in LEVELS for item in level):
        raise HTTPException(status_code=422, detail="Invalid customer level")

    filters = []
    params: dict[str, object] = {"limit": size, "offset": (page - 1) * size}
    if level:
        filters.append("customer_scores.level = ANY(:levels)")
        params["levels"] = level
    if q:
        filters.append(
            "(accounts.id::text ILIKE :query ESCAPE '\\' "
            "OR accounts.email ILIKE :query ESCAPE '\\')"
        )
        escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params["query"] = f"%{escaped}%"
    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    direction = "ASC" if order == "asc" else "DESC"
    sort_column = SORT_COLUMNS[sort_by]
    query = text(
        f"""
        SELECT accounts.id, accounts.email, accounts.balance,
               accounts."totalReplenished" AS total_replenished,
               customer_scores.score, customer_scores.level, customer_scores.loyalty,
               customer_scores.reasons, customer_scores.expected_loss_cents
        FROM public.accounts AS accounts
        JOIN app.customer_scores AS customer_scores
          ON customer_scores.customer_id = accounts.id
        {where_clause}
        ORDER BY {sort_column} {direction} NULLS LAST, accounts.id ASC
        LIMIT :limit OFFSET :offset
        """
    )
    count_query = text(
        f"""
        SELECT count(*)
        FROM public.accounts AS accounts
        JOIN app.customer_scores AS customer_scores
          ON customer_scores.customer_id = accounts.id
        {where_clause}
        """
    )
    with request.app.state.engine.connect() as connection:
        rows = connection.execute(query, params).mappings().all()
        total = connection.execute(count_query, params).scalar_one()

    items = []
    for row in rows:
        reasons = row["reasons"] or []
        items.append(
            {
                "id": row["id"],
                "email": row["email"],
                "balanceCents": row["balance"],
                "totalReplenishedCents": row["total_replenished"],
                "score": row["score"],
                "level": row["level"],
                "loyalty": row["loyalty"],
                "topReason": reasons[0]["explanation"] if reasons else None,
                "expectedLossCents": row["expected_loss_cents"],
            }
        )
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/{customer_id}", summary="Карточка клиента")
def get_customer(customer_id: int, request: Request) -> dict:
    with request.app.state.engine.connect() as connection:
        customer = connection.execute(
            text(
                """
                SELECT accounts.id, accounts.email, accounts.balance,
                       accounts."withdrawBalance" AS withdraw_balance,
                       accounts."totalReplenished" AS total_replenished,
                       accounts."bonusBalance" AS bonus_balance,
                       accounts."bonusState" AS bonus_state,
                       scores.score, scores.level, scores.loyalty,
                       scores.expected_loss_cents, scores.reasons, scores.data_warnings
                FROM public.accounts AS accounts
                JOIN app.customer_scores AS scores ON scores.customer_id = accounts.id
                WHERE accounts.id = :customer_id
                """
            ),
            {"customer_id": customer_id},
        ).mappings().first()
        if customer is None:
            raise HTTPException(status_code=404, detail="Customer not found")
        services = connection.execute(
            text(
                """
                SELECT services.id, services.name, services."paymentTerm" AS payment_term,
                       services."autoProlong" AS auto_prolong, services."createdAt" AS created_at,
                       services."expiresAt" AS expires_at, services.status, services.price,
                       scores.score, scores.feature_contributions, scores.value_cents,
                       scores.expected_loss_cents
                FROM public.services AS services
                LEFT JOIN app.service_scores AS scores ON scores.service_id = services.id
                WHERE services."ownerId" = :customer_id
                ORDER BY services.id
                """
            ),
            {"customer_id": customer_id},
        ).mappings().all()

    return {
        "id": customer["id"],
        "email": customer["email"],
        "balanceCents": customer["balance"],
        "withdrawBalanceCents": customer["withdraw_balance"],
        "totalReplenishedCents": customer["total_replenished"],
        "bonusBalanceCents": customer["bonus_balance"],
        "bonusState": customer["bonus_state"],
        "score": customer["score"],
        "level": customer["level"],
        "loyalty": customer["loyalty"],
        "expectedLossCents": customer["expected_loss_cents"],
        "reasons": customer["reasons"] or [],
        "dataWarnings": customer["data_warnings"] or [],
        "services": [
            {
                "id": service["id"],
                "name": service["name"],
                "paymentTerm": service["payment_term"],
                "autoProlong": service["auto_prolong"],
                "createdAt": service["created_at"],
                "expiresAt": service["expires_at"],
                "status": service["status"],
                "priceCents": service["price"],
                "score": service["score"],
                "featureContributions": service["feature_contributions"] or [],
                "valueCents": service["value_cents"] or 0,
                "expectedLossCents": service["expected_loss_cents"] or 0,
            }
            for service in services
        ],
    }