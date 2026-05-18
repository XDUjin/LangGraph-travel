"""购票相关数据模型"""

from typing import List, Optional
from pydantic import BaseModel, Field


class BookingLink(BaseModel):
    """单个平台的购票链接"""
    platform: str = Field(..., description="平台名称: 携程/美团/飞猪")
    platform_key: str = Field(..., description="平台标识符: ctrip/meituan/fliggy")
    url: str = Field(..., description="搜索/购票URL")
    display_name: str = Field(..., description="展示名称")


class TicketBookingItem(BaseModel):
    """单个景点的购票信息"""
    attraction_name: str = Field(..., description="景点名称")
    city: str = Field(..., description="所在城市")
    day_index: int = Field(..., description="第几天（从0开始）")
    needs_ticket: bool = Field(..., description="是否需要购票")
    estimated_price_min: int = Field(default=0, description="预估最低票价（元）")
    estimated_price_max: int = Field(default=0, description="预估最高票价（元）")
    ticket_type_note: str = Field(default="", description="票种说明，如旺季/淡季/优惠票")
    booking_links: List[BookingLink] = Field(default=[], description="各平台购票链接")
    note: str = Field(default="", description="购票备注（如需提前预约、免票政策等）")
    free_reason: Optional[str] = Field(default=None, description="免票原因")


class TicketBookingRequest(BaseModel):
    """购票分析请求"""
    city: str = Field(..., description="旅行目的地城市")
    trip_plan_summary: List[dict] = Field(..., description="行程中所有景点的精简信息列表")

    class Config:
        json_schema_extra = {
            "example": {
                "city": "北京",
                "trip_plan_summary": [
                    {"name": "故宫", "city": "北京", "day_index": 0, "category": "历史文化", "ticket_price": 60},
                    {"name": "天安门广场", "city": "北京", "day_index": 0, "category": "广场", "ticket_price": 0}
                ]
            }
        }


class TicketBookingResponse(BaseModel):
    """购票分析响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="消息")
    items: List[TicketBookingItem] = Field(default=[], description="各景点购票信息")
    total_min_cost: int = Field(default=0, description="预估最低总票价")
    total_max_cost: int = Field(default=0, description="预估最高总票价")
    paid_count: int = Field(default=0, description="需要购票的景点数量")
