"""门票查询与购票链接生成服务"""

import json
import logging
import urllib.parse
from typing import List

from langchain_core.messages import HumanMessage, SystemMessage

from .llm_service import get_llm
from ..models.ticket_schemas import (
    BookingLink,
    TicketBookingItem,
    TicketBookingRequest,
    TicketBookingResponse,
)

logger = logging.getLogger(__name__)

TICKET_SYSTEM_PROMPT = """你是一位专业的中国旅游顾问，精通全国各地景区的门票制度和预订方式。

你的任务是分析一份景点列表，判断每个景点是否需要购买门票，并提供预估价格范围。

严格按照以下JSON数组格式返回，不要有任何多余内容，不要有markdown代码块标记：
[
  {
    "attraction_name": "景点名称（与输入完全一致）",
    "needs_ticket": true,
    "estimated_price_min": 最低票价整数（元，免费则为0）,
    "estimated_price_max": 最高票价整数（元，免费则为0）,
    "ticket_type_note": "票种说明，例如：成人票60元/学生票30元，旺季价格更高",
    "note": "购票注意事项，例如：需提前网上实名预约，限流景区建议提前购买",
    "free_reason": "若免费，注明原因（如公共广场、免费公园等），否则为null"
  }
]

判断规则：
1. 有围墙收费的著名景区（故宫、兵马俑、黄山等）：needs_ticket = true
2. 公共广场、步行街、古街区通常：needs_ticket = false
3. 博物馆：很多是免费预约制，needs_ticket = false，但note需注明需预约
4. 公园：依据实际情况，如颐和园收费、天坛收费，城市公共公园免费
5. 价格范围要反映2026年实际票价
6. attraction_name字段必须与输入的景点名称完全一致"""


def generate_booking_links(attraction_name: str, city: str) -> List[BookingLink]:
    """生成各平台购票搜索链接（纯Python确定性生成，无LLM）"""
    encoded_name = urllib.parse.quote(attraction_name)
    encoded_name_ticket = urllib.parse.quote(f"{attraction_name}门票")
    encoded_baidu = urllib.parse.quote(f"{city} {attraction_name} 门票 在线预订")

    return [
        # 携程——景点门票专属搜索（SPA hash路由）
        BookingLink(
            platform="高德地图",
            platform_key="ctrip",
            url=f"https://you.ctrip.com/searchSite/?query={encoded_name_ticket}&isAnswered=&searchtype=1",
            display_name="携程购票",
        )
    ]


def _extract_json_array(text: str) -> str:
    """从LLM响应中提取JSON数组字符串"""
    text = text.strip()
    # 去掉 markdown 代码块
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        return text[start:end].strip()
    if "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
        return text[start:end].strip()
    # 查找第一个 [ 到最后一个 ]
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


async def analyze_tickets(request: TicketBookingRequest) -> TicketBookingResponse:
    """核心服务函数：调用LLM分析景点购票需求，生成购票链接"""
    llm = get_llm()

    # 构建给 LLM 的景点列表
    attraction_list = [
        {"name": a.get("name", ""), "category": a.get("category", "景点")}
        for a in request.trip_plan_summary
    ]
    attraction_list_json = json.dumps(attraction_list, ensure_ascii=False, indent=2)

    user_prompt = (
        f"请分析以下{request.city}的景点列表，判断哪些需要购票：\n\n"
        f"{attraction_list_json}\n\n"
        f"只返回JSON数组，不要有任何其他内容。"
    )

    messages = [
        SystemMessage(content=TICKET_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ]

    logger.info(f"调用LLM分析 {len(attraction_list)} 个景点的购票信息...")
    try:
        response = await llm.ainvoke(messages)
        raw_content = response.content
        logger.debug(f"LLM响应原文: {raw_content[:500]}")
        json_str = _extract_json_array(raw_content)
        llm_results: list = json.loads(json_str)
    except Exception as e:
        logger.error(f"LLM购票分析失败: {e}")
        raise RuntimeError(f"LLM分析景点购票信息失败: {e}") from e

    # 将 LLM 结果映射回原始景点列表，并附加购票链接
    items: List[TicketBookingItem] = []
    for attr in request.trip_plan_summary:
        name = attr.get("name", "")
        day_index = attr.get("day_index", 0)

        # 按景点名称匹配 LLM 输出（去除首尾空白后比较）
        llm_item = next(
            (r for r in llm_results if r.get("attraction_name", "").strip() == name.strip()),
            None,
        )

        if llm_item is None:
            # 兜底：若 LLM 未返回该景点，依据原始 ticket_price 判断
            needs_ticket = (attr.get("ticket_price") or 0) > 0
            llm_item = {
                "needs_ticket": needs_ticket,
                "estimated_price_min": 0,
                "estimated_price_max": attr.get("ticket_price") or 0,
                "ticket_type_note": "",
                "note": "",
                "free_reason": None,
            }

        needs_ticket = bool(llm_item.get("needs_ticket", False))


        booking_links = generate_booking_links(name, request.city) if needs_ticket else []

        items.append(
            TicketBookingItem(
                attraction_name=name,
                city=request.city,
                day_index=day_index,
                needs_ticket=needs_ticket,
                estimated_price_min=int(llm_item.get("estimated_price_min") or 0),
                estimated_price_max=int(llm_item.get("estimated_price_max") or 0),
                ticket_type_note=llm_item.get("ticket_type_note") or "",
                booking_links=booking_links,
                note=llm_item.get("note") or "",
                free_reason=llm_item.get("free_reason"),
            )
        )

    paid_items = [i for i in items if i.needs_ticket]
    total_min = sum(i.estimated_price_min for i in paid_items)
    total_max = sum(i.estimated_price_max for i in paid_items)

    logger.info(f"购票分析完成：{len(paid_items)}/{len(items)} 个景点需要购票")

    return TicketBookingResponse(
        success=True,
        message=f"分析完成，共 {len(paid_items)} 个景点需要购票",
        items=items,
        total_min_cost=total_min,
        total_max_cost=total_max,
        paid_count=len(paid_items),
    )
