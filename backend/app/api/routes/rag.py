"""RAG 问答 API 路由"""

import logging

from fastapi import APIRouter, HTTPException

from ...models.schemas import (
    RAGQueryRequest,
    RAGQueryResponse,
    RAGStatusResponse,
    RAGSource,
)
from ...services.rag_service import get_rag_service

router = APIRouter(prefix="/rag", tags=["RAG 问答"])
logger = logging.getLogger(__name__)


@router.post(
    "/query",
    response_model=RAGQueryResponse,
    summary="RAG 问答",
    description="基于知识库的旅行问答",
)
async def rag_query(request: RAGQueryRequest):
    """执行 RAG 问答"""
    try:
        logger.info(f"收到 RAG 问答请求: {request.question[:50]}...")

        rag = get_rag_service()
        result = rag.query(request.question)

        sources = [
            RAGSource(content=s["content"], source=s["source"])
            for s in result["sources"]
        ]

        return RAGQueryResponse(
            success=True,
            message="回答生成成功",
            answer=result["answer"],
            sources=sources,
            intent=result.get("intent", "travel_rag"),
        )

    except Exception as e:
        logger.error(f"RAG 问答失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"RAG 问答失败: {str(e)}",
        )


@router.get(
    "/status",
    response_model=RAGStatusResponse,
    summary="RAG 服务状态",
    description="查询 RAG 服务和知识库状态",
)
async def rag_status():
    """查询 RAG 服务状态"""
    try:
        rag = get_rag_service()
        status = rag.get_status()
        return RAGStatusResponse(**status)
    except Exception as e:
        logger.error(f"查询 RAG 状态失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"查询 RAG 状态失败: {str(e)}",
        )


@router.post(
    "/reindex",
    summary="重新索引知识库",
    description="强制重建知识库索引",
)
async def rag_reindex():
    """强制重建知识库索引"""
    try:
        rag = get_rag_service()
        result = rag.ingest_documents(force_rebuild=True)
        return {
            "success": True,
            "message": "知识库重新索引完成",
            "data": result,
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"重新索引失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"重新索引失败: {str(e)}")
