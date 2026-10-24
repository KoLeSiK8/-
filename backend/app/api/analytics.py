from fastapi import APIRouter, Depends, Request

from ..analytics.summary import build_summary
from ..analytics.timeline import build_timeline
from ..auth.deps import require_user

router = APIRouter(dependencies=[Depends(require_user)])


@router.get("/summary", summary="Сводка для дашборда (те же числа, что в /metrics)")
def get_summary(request: Request) -> dict:
    return build_summary(request.app.state.engine)


@router.get("/churn-timeline", summary="График оттока: факт, оценка, прогноз (в услугах)")
def get_churn_timeline(request: Request) -> dict:
    return build_timeline(request.app.state.engine)