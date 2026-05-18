"""知识库文档索引脚本

用法:
  python ingest_knowledge.py              # 增量索引（跳过已有）
  python ingest_knowledge.py --rebuild    # 强制重建（清空后重新索引）
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app.services.rag_service import get_rag_service


def main():
    force = "--rebuild" in sys.argv
    print("=" * 50)
    print("开始索引知识库文档...")
    if force:
        print("模式: 强制重建")
    else:
        print("模式: 增量索引")
    print("=" * 50)

    rag = get_rag_service()
    result = rag.ingest_documents(force_rebuild=force)

    print(f"\n结果: {result}")
    print("=" * 50)


if __name__ == "__main__":
    main()
