"""RAG 检索增强生成服务（Agentic RAG + 混合检索 + RRF 重排序）"""

import os
import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any

from langchain_community.embeddings import HuggingFaceBgeEmbeddings
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from ..tools.pdf_table_loader import load_pdf_with_tables
from langchain_community.retrievers import BM25Retriever
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

from ..config import get_settings
from ..services.llm_service import get_llm

logger = logging.getLogger(__name__)

# 意图分类 prompt
INTENT_CLASSIFY_PROMPT = """你是一个意图分类器。根据用户的问题，判断它属于以下哪个意图：

1. "travel_rag" — 与旅行相关的问题，包括：景点推荐、景点介绍、旅游攻略、美食推荐、住宿建议、交通指南、旅行贴士、行程规划等。这类问题需要从知识库中检索相关信息来回答。

2. "general" — 非旅行相关的通用问题，包括：闲聊问候、自我介绍、数学计算、编程问题、新闻时事、与旅行无关的知识问答等。这类问题不需要旅行知识库。

请只返回一个 JSON，格式如下，不要返回其他内容：
{{"intent": "travel_rag 或 general", "reason": "简短说明分类原因"}}

用户问题: {question}"""

# 通用回答 prompt
GENERAL_ANSWER_PROMPT = """你是一个友好的 AI 助手。请用中文简洁地回答用户的问题。
如果用户问的是旅行相关的问题，建议他们使用旅行规划功能或询问旅行知识库相关问题。

用户问题: {question}"""

_rag_service_instance: Optional["RAGService"] = None


class RAGService:
    """RAG 检索增强生成服务"""

    def __init__(self):
        settings = get_settings()
        self.chromadb_path = settings.chromadb_path
        self.collection_name = settings.chromadb_collection
        self.embedding_model_name = settings.embedding_model
        self.top_k = settings.rag_top_k
        self.knowledge_base_path = settings.knowledge_base_path
        self._hf_endpoint = settings.hf_endpoint

        self._embeddings = None
        self._vectorstore = None
        self._bm25_retriever = None
        self._vector_retriever = None
        self._chain = None
        self._all_chunks: List[Document] = []

    def _init_embeddings(self):
        """初始化 embedding 模型"""
        if self._embeddings is None:
            # 设置 Hugging Face 镜像源（仅本项目生效）
            if self._hf_endpoint:
                os.environ["HF_ENDPOINT"] = self._hf_endpoint
                logger.info(f"Hugging Face 镜像源: {self._hf_endpoint}")

            logger.info(f"加载 embedding 模型: {self.embedding_model_name}")
            self._embeddings = HuggingFaceBgeEmbeddings(
                model_name=self.embedding_model_name,
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True},
                query_instruction="为这个句子生成表示以用于检索相关文章：",
            )
            logger.info("Embedding 模型加载完成")
        return self._embeddings

    def _init_vectorstore(self):
        """初始化或连接 ChromaDB 向量存储"""
        if self._vectorstore is None:
            embeddings = self._init_embeddings()
            os.makedirs(self.chromadb_path, exist_ok=True)

            self._vectorstore = Chroma(
                collection_name=self.collection_name,
                embedding_function=embeddings,
                persist_directory=self.chromadb_path,
            )
            count = self._vectorstore._collection.count()
            logger.info(
                f"ChromaDB 已连接: {self.chromadb_path}, "
                f"集合: {self.collection_name}, 文档数: {count}"
            )
        return self._vectorstore

    def _load_all_documents(self) -> List[Document]:
        """从知识库目录加载所有支持格式的文档（.md + .pdf）"""
        kb_path = Path(self.knowledge_base_path)
        if not kb_path.exists():
            return []

        all_docs: List[Document] = []

        # 加载 Markdown 文件
        try:
            md_loader = DirectoryLoader(
                str(kb_path),
                glob="**/*.md",
                loader_cls=TextLoader,
                loader_kwargs={"encoding": "utf-8"},
                use_multithreading=True,
            )
            md_docs = md_loader.load()
            logger.info(f"加载了 {len(md_docs)} 个 Markdown 文档")
            all_docs.extend(md_docs)
        except Exception as e:
            logger.warning(f"加载 Markdown 文档失败: {e}")

        # 加载 PDF 文件（表格感知，支持跨页合并）
        try:
            pdf_files = list(kb_path.glob("**/*.pdf"))
            for pdf_file in pdf_files:
                pdf_docs = load_pdf_with_tables(str(pdf_file))
                all_docs.extend(pdf_docs)
            logger.info(f"加载了 {len(pdf_files)} 个 PDF 文档")
        except Exception as e:
            logger.warning(f"加载 PDF 文档失败: {e}")

        return all_docs

    def _split_documents(self, documents: List[Document]) -> List[Document]:
        """将文档分块"""
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=256,
            chunk_overlap=32,
            separators=["\n## ", "\n### ", "\n\n", "\n", "。", "；", " "],
        )
        return text_splitter.split_documents(documents)

    def _load_chunks_for_bm25(self):
        """从知识库目录加载文档并分块，供 BM25 检索器使用"""
        try:
            documents = self._load_all_documents()
            if not documents:
                return

            self._all_chunks = self._split_documents(documents)
            logger.info(f"为 BM25 加载了 {len(self._all_chunks)} 个文档块")
        except Exception as e:
            logger.warning(f"为 BM25 加载文档失败: {e}")

    @staticmethod
    def _rrf_fusion(
        ranked_lists: List[List[Document]],
        k: int = 60,
        top_n: int = 5,
    ) -> List[Document]:
        """RRF (Reciprocal Rank Fusion) 重排序算法

        对多个检索器的排序结果进行融合，公式: score(d) = Σ 1 / (k + rank_i(d))

        Args:
            ranked_lists: 各检索器返回的有序文档列表
            k: 平滑常数（默认 60）
            top_n: 最终返回的文档数量
        """
        scores: Dict[str, float] = {}
        doc_map: Dict[str, Document] = {}

        for ranked_docs in ranked_lists:
            for rank, doc in enumerate(ranked_docs):
                doc_id = f"{doc.metadata.get('source', '')}_{doc.page_content[:80]}"
                scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
                if doc_id not in doc_map:
                    doc_map[doc_id] = doc

        sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)
        return [doc_map[doc_id] for doc_id in sorted_ids[:top_n]]

    def _build_chain(self):
        """构建混合检索 + RRF 重排序 + LLM 生成链"""
        if self._chain is not None:
            return

        vectorstore = self._init_vectorstore()

        # 向量检索器
        self._vector_retriever = vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={"k": self.top_k},
        )

        # BM25 关键词检索器：如果内存中没有 chunks，尝试从知识库重新加载
        if not self._all_chunks:
            self._load_chunks_for_bm25()

        if self._all_chunks:
            self._bm25_retriever = BM25Retriever.from_documents(
                self._all_chunks,
                k=self.top_k,
            )
            logger.info(f"BM25 检索器初始化完成，文档数: {len(self._all_chunks)}")
        else:
            logger.warning("无文档数据，BM25 检索器未初始化，仅使用语义检索")
            self._bm25_retriever = None

        llm = get_llm()

        prompt = ChatPromptTemplate.from_template(
            """你是一个专业的旅行顾问。请根据以下检索到的参考资料来回答用户的旅行相关问题。
如果参考资料中没有相关信息，请根据你的知识回答，但要说明这不是基于知识库的回答。
请用中文回答，语言要自然、实用。

参考资料:
{context}

用户问题: {question}

回答:"""
        )

        def hybrid_retrieve(question: str) -> str:
            """执行混合检索 + RRF 重排序"""
            ranked_lists = []

            # 向量语义检索
            vector_docs = self._vector_retriever.invoke(question)
            ranked_lists.append(vector_docs)
            logger.info(f"语义检索返回 {len(vector_docs)} 个文档")

            # BM25 关键词检索
            if self._bm25_retriever is not None:
                bm25_docs = self._bm25_retriever.invoke(question)
                ranked_lists.append(bm25_docs)
                logger.info(f"BM25 检索返回 {len(bm25_docs)} 个文档")

            # RRF 融合重排序
            if len(ranked_lists) > 1:
                fused_docs = self._rrf_fusion(ranked_lists, k=60, top_n=self.top_k)
            else:
                fused_docs = ranked_lists[0][:self.top_k]

            logger.info(f"RRF 融合后返回 {len(fused_docs)} 个文档")

            formatted = []
            for i, doc in enumerate(fused_docs, 1):
                source = doc.metadata.get("source", "未知来源")
                formatted.append(f"[{i}] (来源: {source})\n{doc.page_content}")
            return "\n\n".join(formatted)

        self._chain = (
            {"context": RunnablePassthrough() | hybrid_retrieve, "question": RunnablePassthrough()}
            | prompt
            | llm
            | StrOutputParser()
        )
        logger.info("混合检索 RAG chain 构建完成")

    def ingest_documents(self, force_rebuild: bool = False) -> Dict[str, Any]:
        """加载知识库文档并索引到 ChromaDB"""
        kb_path = Path(self.knowledge_base_path)
        if not kb_path.exists():
            raise FileNotFoundError(f"知识库目录不存在: {self.knowledge_base_path}")

        vectorstore = self._init_vectorstore()

        existing_count = vectorstore._collection.count()
        if existing_count > 0 and not force_rebuild:
            logger.info(f"ChromaDB 已有 {existing_count} 个文档块，跳过索引")
            return {"status": "skipped", "existing_count": existing_count}

        if force_rebuild and existing_count > 0:
            logger.info("强制重建：清空现有集合...")
            vectorstore._collection.delete(where={})
            logger.info("集合已清空")

        logger.info(f"从 {self.knowledge_base_path} 加载文档（.md + .pdf）...")
        documents = self._load_all_documents()
        logger.info(f"加载了 {len(documents)} 个文档")

        if not documents:
            return {"status": "no_documents", "loaded": 0}

        chunks = self._split_documents(documents)
        logger.info(f"分割为 {len(chunks)} 个文档块")

        vectorstore.add_documents(chunks)
        self._all_chunks = chunks

        self._chain = None
        self._bm25_retriever = None

        logger.info(f"索引完成: {len(chunks)} 个文档块已写入 ChromaDB")
        return {
            "status": "success",
            "documents_loaded": len(documents),
            "chunks_created": len(chunks),
        }

    def _classify_intent(self, question: str) -> str:
        """使用 LLM 对用户问题进行意图分类"""
        llm = get_llm()
        prompt = INTENT_CLASSIFY_PROMPT.format(question=question)

        try:
            response = llm.invoke(prompt)
            content = response.content.strip()

            # 尝试从回复中提取 JSON
            # 处理可能被 markdown 包裹的情况
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            # 提取 JSON 对象
            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end > start:
                result = json.loads(content[start:end])
                intent = result.get("intent", "travel_rag")
                reason = result.get("reason", "")
                logger.info(f"意图分类: {intent}, 原因: {reason}")
                return intent if intent in ("travel_rag", "general") else "travel_rag"

            logger.warning(f"意图分类返回格式异常: {content}")
            return "travel_rag"

        except Exception as e:
            logger.error(f"意图分类失败: {e}，默认走 RAG 路由")
            return "travel_rag"

    def _direct_answer(self, question: str) -> str:
        """直接调用 LLM 回答（不走 RAG 检索）"""
        llm = get_llm()
        prompt = GENERAL_ANSWER_PROMPT.format(question=question)

        try:
            response = llm.invoke(prompt)
            return response.content.strip()
        except Exception as e:
            logger.error(f"LLM 直接回答失败: {e}")
            return f"抱歉，回答失败: {str(e)}"

    def query(self, question: str) -> Dict[str, Any]:
        """执行 Agentic RAG 查询（带意图路由）"""
        # Step 1: 意图分类
        intent = self._classify_intent(question)
        logger.info(f"路由决策: intent={intent}")

        # Step 2: 根据意图路由
        if intent == "general":
            answer = self._direct_answer(question)
            return {
                "answer": answer,
                "sources": [],
                "intent": intent,
            }

        # Step 3: travel_rag → 混合检索 + RRF + LLM 生成
        self._build_chain()

        # 混合检索获取来源（与 chain 内部逻辑一致，避免重复调用 LLM）
        ranked_lists = []
        vector_docs = self._vector_retriever.invoke(question)
        ranked_lists.append(vector_docs)
        if self._bm25_retriever is not None:
            bm25_docs = self._bm25_retriever.invoke(question)
            ranked_lists.append(bm25_docs)

        if len(ranked_lists) > 1:
            fused_docs = self._rrf_fusion(ranked_lists, k=60, top_n=self.top_k)
        else:
            fused_docs = ranked_lists[0][:self.top_k]

        sources = []
        for doc in fused_docs:
            sources.append({
                "content": doc.page_content[:200],
                "source": doc.metadata.get("source", "未知"),
            })

        answer = self._chain.invoke(question)

        return {
            "answer": answer,
            "sources": sources,
            "intent": intent,
        }

    def get_status(self) -> Dict[str, Any]:
        """获取 RAG 服务状态"""
        try:
            vectorstore = self._init_vectorstore()
            count = vectorstore._collection.count()
            return {
                "status": "ready",
                "document_count": count,
                "chromadb_path": self.chromadb_path,
                "collection_name": self.collection_name,
                "embedding_model": self.embedding_model_name,
                "knowledge_base_path": self.knowledge_base_path,
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }


def get_rag_service() -> RAGService:
    """获取 RAG 服务实例（单例模式）"""
    global _rag_service_instance
    if _rag_service_instance is None:
        _rag_service_instance = RAGService()
    return _rag_service_instance


def reset_rag_service():
    """重置 RAG 服务实例"""
    global _rag_service_instance
    _rag_service_instance = None
