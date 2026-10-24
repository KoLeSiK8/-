from fastapi import APIRouter, Depends, Request

from ..analytics.summary import build_summary
from ..analytics.timeline import build_timeline
from ..auth.deps import require_user

router = APIRouter(dependencies=[Depends(require_user)])


@router.get("/summary")
def get_summary(request: Request) -> dict:
    return build_summary(request.app.state.engine)


@router.get("/churn-timeline")
def get_churn_timeline(request: Request) -> dict:
    return build_timeline(request.app.state.engine)