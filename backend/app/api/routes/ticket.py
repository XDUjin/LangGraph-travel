"""购票分析API路由"""

from fastapi import APIRouter, HTTPException
import logging

from ...models.ticket_schemas import TicketBookingRequest, TicketBookingResponse
from ...services.ticket_service import analyze_tickets

router = APIRouter(prefix="/trip", tags=["购票"])
logger = logging.getLogger(__name__)


@router.post(
    "/book-tickets",
    response_model=TicketBookingResponse,
    summary="分析景点购票需求",
    description="基于旅行计划中的景点列表，分析哪些需要购票并生成各平台购票链接",
)
async def book_tickets(request: TicketBookingRequest):
    """
    分析旅行计划中所有景点的购票需求，返回：
    - 每个景点是否需要购票及预估价格
    - 携程/美团/飞猪三平台的购票搜索链接
    - 汇总票价区间和需购票景点数量
    """
    try:
        logger.info(
            f"收到购票分析请求: 城市={request.city}, 景点数={len(request.trip_plan_summary)}"
        )
        result = await analyze_tickets(request)
        return result
    except Exception as e:
        logger.error(f"购票分析失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"购票分析失败: {str(e)}")
