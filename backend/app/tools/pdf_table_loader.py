"""PDF 表格感知加载器（支持跨页表格合并）"""

import logging
from pathlib import Path
from typing import List, Optional

import pdfplumber
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


def _table_to_markdown(table: List[List[str]]) -> str:
    """将二维表格转为 Markdown 格式"""
    if not table or not table[0]:
        return ""

    # 清理单元格中的换行和多余空格
    cleaned = []
    for row in table:
        cleaned.append([
            str(cell).replace("\n", " ").strip() if cell else ""
            for cell in row
        ])

    # 表头
    header = cleaned[0]
    lines = ["| " + " | ".join(header) + " |"]
    lines.append("| " + " | ".join(["---"] * len(header)) + " |")

    # 数据行
    for row in cleaned[1:]:
        # 补齐列数
        padded = row + [""] * (len(header) - len(row))
        lines.append("| " + " | ".join(padded[:len(header)]) + " |")

    return "\n".join(lines)


def _is_continuation_table(
    prev_table: List[List[str]],
    curr_table: List[List[str]],
) -> bool:
    """判断当前页的表格是否是上一页表格的延续

    判断依据：
    1. 列数相同
    2. 当前页表格没有表头（第一行不是表头风格）或表头与上一页一致
    """
    if not prev_table or not curr_table:
        return False

    prev_cols = len(prev_table[0]) if prev_table[0] else 0
    curr_cols = len(curr_table[0]) if curr_table[0] else 0

    if prev_cols != curr_cols or prev_cols == 0:
        return False

    # 如果当前页第一行与上一页表头相同，视为带表头的延续
    if curr_table[0] == prev_table[0]:
        return True

    # 如果当前页第一行明显是数据行（非表头），视为延续
    # 启发式：表头通常较短且不含纯数字
    first_row = curr_table[0]
    numeric_count = sum(1 for cell in first_row if cell and cell.replace(".", "").replace("-", "").isdigit())
    if numeric_count < len(first_row) * 0.5:
        # 非数字为主，可能是新表头 → 检查是否与上一页表头相似
        if curr_table[0] == prev_table[0]:
            return True

    # 默认视为延续（列数相同的情况下）
    return True


def _merge_page_texts_and_tables(
    pages_data: List[dict],
) -> List[str]:
    """合并各页的文本和表格，处理跨页表格

    返回合并后的文档片段列表
    """
    merged_parts: List[str] = []
    pending_table: Optional[List[List[str]]] = None

    for page_info in pages_data:
        page_num = page_info["page"]
        text_blocks = page_info["text_blocks"]
        tables = page_info["tables"]

        # 先处理文本
        page_text = "\n".join(text_blocks).strip()
        if page_text:
            # 如果有未完成的跨页表格，先输出它
            if pending_table:
                md = _table_to_markdown(pending_table)
                if md:
                    merged_parts.append(md)
                pending_table = None
            merged_parts.append(page_text)

        # 处理表格
        for table in tables:
            if not table or not table[0]:
                continue

            if pending_table is not None:
                # 检查是否是跨页延续
                if _is_continuation_table(pending_table, table):
                    # 跳过重复表头，追加数据行
                    if table[0] == pending_table[0]:
                        pending_table.extend(table[1:])
                    else:
                        pending_table.extend(table)
                    continue
                else:
                    # 不是延续，输出之前的表格
                    md = _table_to_markdown(pending_table)
                    if md:
                        merged_parts.append(md)
                    pending_table = None

            # 判断表格是否跨到下一页（表格在页面底部且可能被截断）
            # 启发式：如果表格行数 >= 3 且位于页面后半部分，可能是跨页表格
            pending_table = table

        # 页面结束，如果有待定表格且下一页不延续，这里先保留
        # （在循环结束或下一页处理时决定）

    # 输出最后一个待定表格
    if pending_table:
        md = _table_to_markdown(pending_table)
        if md:
            merged_parts.append(md)

    return merged_parts


class PDFTableLoader:
    """PDF 表格感知加载器

    使用 pdfplumber 提取 PDF 内容，自动检测并合并跨页表格，
    将表格转为 Markdown 格式以提升 RAG 检索质量。
    """

    def __init__(self, file_path: str):
        self.file_path = str(file_path)

    def load(self) -> List[Document]:
        """加载 PDF 并返回处理后的文档列表"""
        if not Path(self.file_path).exists():
            logger.warning(f"PDF 文件不存在: {self.file_path}")
            return []

        try:
            pages_data = self._extract_pages()
            parts = _merge_page_texts_and_tables(pages_data)

            if not parts:
                return []

            # 将各部分合并为一个文档（保留页码元数据）
            full_text = "\n\n".join(parts)
            doc = Document(
                page_content=full_text,
                metadata={
                    "source": self.file_path,
                    "file_type": "pdf",
                },
            )
            return [doc]

        except Exception as e:
            logger.error(f"PDF 解析失败 {self.file_path}: {e}")
            return []

    def _extract_pages(self) -> List[dict]:
        """逐页提取文本和表格"""
        pages_data = []

        with pdfplumber.open(self.file_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_info = {
                    "page": i + 1,
                    "text_blocks": [],
                    "tables": [],
                }

                # 提取文本
                text = page.extract_text()
                if text:
                    page_info["text_blocks"].append(text.strip())

                # 提取表格
                tables = page.extract_tables()
                for table in tables:
                    if table:
                        page_info["tables"].append(table)

                pages_data.append(page_info)

        return pages_data


def load_pdf_with_tables(file_path: str) -> List[Document]:
    """便捷函数：加载 PDF 并处理跨页表格"""
    loader = PDFTableLoader(file_path)
    return loader.load()
