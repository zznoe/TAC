"""
知识库服务 - RAG 实现
支持向量数据库存储和检索公司研报、财报等长文本信息
"""
import os
import json
import threading
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

_thread_local = threading.local()

try:
    from chromadb.config import Settings as ChromaSettings
except ImportError:
    ChromaSettings = None

from tradingagents.utils.logging_init import get_logger

logger = get_logger("knowledge_service")


@dataclass
class DocumentChunk:
    """文档片段"""
    content: str
    metadata: Dict[str, Any]
    embedding: Optional[List[float]] = None


@dataclass
class SearchResult:
    """检索结果"""
    content: str
    metadata: Dict[str, Any]
    score: float


class BaseVectorStore:
    """向量存储基类"""

    def add_documents(self, collection_name: str, documents: List[DocumentChunk]) -> None:
        raise NotImplementedError

    def similarity_search(
        self, collection_name: str, query: str, top_k: int = 5
    ) -> List[SearchResult]:
        raise NotImplementedError

    def delete_collection(self, collection_name: str) -> None:
        raise NotImplementedError


class ChromaDBStore(BaseVectorStore):
    """ChromaDB 向量存储实现"""

    def __init__(self, persist_directory: str = "./data/knowledge_base"):
        if ChromaSettings is None:
            raise ImportError("chromadb not installed. Run: pip install chromadb")

        os.makedirs(persist_directory, exist_ok=True)
        self.persist_directory = persist_directory

        from chromadb import PersistentClient
        self.client = PersistentClient(path=persist_directory)
        logger.info(f"📚 ChromaDB 知识库初始化完成，存储路径: {persist_directory}")

    def _get_or_create_collection(self, collection_name: str):
        return self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    def add_documents(self, collection_name: str, documents: List[DocumentChunk]) -> None:
        collection = self._get_or_create_collection(collection_name)

        ids = []
        embeddings = []
        contents = []
        metadatas = []

        for i, doc in enumerate(documents):
            doc_id = f"doc_{datetime.now().timestamp()}_{i}"
            ids.append(doc_id)

            if doc.embedding is not None:
                embeddings.append(doc.embedding)
            else:
                embeddings.append([])

            contents.append(doc.content)
            metadatas.append(doc.metadata)

        try:
            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=contents,
                metadatas=metadatas
            )
            logger.info(f"✅ 已添加 {len(documents)} 个文档到集合 {collection_name}")
        except Exception as e:
            logger.error(f"添加文档失败: {e}")
            raise

    def similarity_search(
        self, collection_name: str, query: str, top_k: int = 5
    ) -> List[SearchResult]:
        collection = self._get_or_create_collection(collection_name)

        try:
            results = collection.query(
                query_texts=[query],
                n_results=top_k
            )

            search_results = []
            if results.get("documents") and results["documents"][0]:
                for i, content in enumerate(results["documents"][0]):
                    metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
                    distance = results["distances"][0][i] if results.get("distances") else 0.0
                    score = 1.0 - distance

                    search_results.append(SearchResult(
                        content=content,
                        metadata=metadata,
                        score=score
                    ))

            return search_results
        except Exception as e:
            logger.error(f"检索失败: {e}")
            return []

    def delete_collection(self, collection_name: str) -> None:
        try:
            self.client.delete_collection(name=collection_name)
            logger.info(f"🗑️ 已删除集合 {collection_name}")
        except Exception as e:
            logger.warning(f"删除集合失败 (可能不存在): {e}")


class KnowledgeService:
    """
    知识库服务 - 提供公司研报、财报的 RAG 能力
    """

    DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"

    def __init__(
        self,
        vector_store: Optional[BaseVectorStore] = None,
        embedding_model: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        初始化知识服务

        Args:
            vector_store: 向量存储实例，默认使用 ChromaDB
            embedding_model:  embedding 模型名称
            config: 配置字典
        """
        self.config = config or {}
        self.embedding_model = embedding_model or self.config.get(
            "embedding_model", self.DEFAULT_EMBEDDING_MODEL
        )

        if vector_store is None:
            persist_dir = self.config.get(
                "knowledge_base_dir",
                os.path.join(os.path.expanduser("~"), "Documents", "TradingAgents", "knowledge_base")
            )
            vector_store = ChromaDBStore(persist_directory=persist_dir)

        self.vector_store = vector_store
        self._embedding_client = None
        self._is_fallback_mode = False
        self._fallback_reason: Optional[str] = None

        logger.info("📚 KnowledgeService 初始化完成")

    def _get_embedding_client(self):
        """获取 embedding 客户端"""
        if self._embedding_client is None:
            try:
                from langchain_openai import OpenAIEmbeddings
                backend_url = self.config.get("backend_url", "https://api.openai.com/v1")
                api_key = self.config.get("api_key", os.getenv("OPENAI_API_KEY", ""))

                self._embedding_client = OpenAIEmbeddings(
                    model=self.embedding_model,
                    base_url=backend_url,
                    api_key=api_key
                )
            except Exception as e:
                logger.warning(f"无法初始化 embedding 客户端: {e}")
                return None
        return self._embedding_client

    def _embed_texts(self, texts: List[str], max_retries: int = 3) -> List[List[float]]:
        """将文本转为 embedding，支持重试"""
        client = self._get_embedding_client()
        if client is None:
            logger.warning("Embedding 客户端不可用，使用零向量（降级模式）")
            self._is_fallback_mode = True
            return [[0.0] * 1536 for _ in texts]

        last_error = None
        for attempt in range(max_retries):
            try:
                result = client.embed_documents(texts)
                if attempt > 0:
                    logger.info(f"✅ Embedding 重试成功 (attempt {attempt + 1})")
                self._is_fallback_mode = False
                return result
            except Exception as e:
                last_error = e
                logger.warning(f"Embedding 失败 (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(0.5 * (attempt + 1))

        logger.error(f"Embedding 重试 {max_retries} 次后仍失败: {last_error}")
        self._is_fallback_mode = True
        return [[0.0] * 1536 for _ in texts]

    def _generate_fallback_response(self, ticker: str, query: str) -> List[Dict[str, Any]]:
        """生成桩数据响应（当向量检索不可用时）"""
        logger.info(f"📚 [RAG 降级] 为 {ticker} 生成桩数据响应")
        return [
            {
                "content": f"【降级数据】关于 {ticker} 的 '{query}'：分析系统当前使用简化检索模式。建议在系统设置中配置有效的向量数据库以获得更精确的分析结果。",
                "metadata": {
                    "ticker": ticker.upper(),
                    "type": "fallback",
                    "source": "system_fallback",
                    "date": datetime.now().strftime("%Y-%m-%d")
                },
                "relevance_score": 0.5
            }
        ]

    def add_company_research_report(
        self,
        ticker: str,
        title: str,
        content: str,
        report_type: str = "research_report",
        source: str = "manual",
        date: Optional[str] = None
    ) -> None:
        """
        添加公司研报或财报文档

        Args:
            ticker: 股票代码
            title: 文档标题
            content: 文档内容
            report_type: 文档类型 (research_report, annual_report, quarterly_report, earnings_call)
            source: 来源
            date: 发布日期
        """
        collection_name = f"company_{ticker.lower()}"

        date_str = date or datetime.now().strftime("%Y-%m-%d")

        chunks = self._split_into_chunks(content)

        document_chunks = [
            DocumentChunk(
                content=chunk,
                metadata={
                    "ticker": ticker.upper(),
                    "title": title,
                    "type": report_type,
                    "source": source,
                    "date": date_str,
                    "chunk_index": i,
                    "total_chunks": len(chunks)
                }
            )
            for i, chunk in enumerate(chunks)
        ]

        embeddings = self._embed_texts(chunks)
        for chunk, embedding in zip(document_chunks, embeddings):
            chunk.embedding = embedding

        self.vector_store.add_documents(collection_name, document_chunks)

        logger.info(f"✅ 已添加 {ticker} 的 {report_type}: {title}")

    def search_company_documents(
        self,
        ticker: str,
        query: str,
        top_k: int = 5,
        report_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        检索公司相关文档

        Args:
            ticker: 股票代码
            query: 查询问题
            top_k: 返回结果数量
            report_type: 可选的文档类型过滤

        Returns:
            检索结果列表
        """
        collection_name = f"company_{ticker.lower()}"

        query_embedding = self._embed_texts([query])[0]

        if self._is_fallback_mode:
            return self._generate_fallback_response(ticker, query)

        from chromadb.errors import NotFoundError
        try:
            results = self.vector_store.similarity_search(
                collection_name, query, top_k
            )
        except Exception as e:
            logger.warning(f"检索 {ticker} 文档失败: {e}")
            self._is_fallback_mode = True
            self._fallback_reason = str(e)
            return self._generate_fallback_response(ticker, query)

        formatted_results = []
        for result in results:
            if report_type and result.metadata.get("type") != report_type:
                continue

            formatted_results.append({
                "content": result.content,
                "metadata": result.metadata,
                "relevance_score": round(result.score, 4)
            })

        logger.info(f"📚 检索 {ticker} 关于 '{query}'，返回 {len(formatted_results)} 条结果")

        return formatted_results

    def _split_into_chunks(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        """将长文本分割成块"""
        chunks = []
        start = 0
        text_length = len(text)

        while start < text_length:
            end = start + chunk_size
            chunk = text[start:end]

            if end < text_length:
                last_period = chunk.rfind("。")
                last_newline = chunk.rfind("\n")
                split_point = max(last_period, last_newline)
                if split_point > chunk_size - 200:
                    chunk = chunk[:split_point + 1]
                    end = start + split_point + 1

            chunks.append(chunk.strip())
            start = end - overlap

        return chunks

    def create_sample_data(self, ticker: str) -> None:
        """创建示例数据用于测试"""
        sample_content = f"""
{ticker} 2024年第四季度财报摘要：

营收方面，公司实现营收 1,234 亿元，同比增长 15%。毛利率为 45%，较去年同期提升 2 个百分点。
净利润为 234 亿元，同比增长 20%。EPS 为 5.67 元。

管理层指引：
- 预计 2025 年营收增长 10%-15%
- 毛利率将进一步提升至 47%
- 资本开支将维持在营收的 8% 左右
- 研发投入将增加至营收的 12%

分析师观点：
- 多家机构维持"买入"评级
- 平均目标价为 180 元，较当前股价有 20% 上涨空间
- 关注焦点：AI 业务增长、云计算市场份额、并购计划
"""
        self.add_company_research_report(
            ticker=ticker,
            title=f"{ticker} 2024Q4 财报分析",
            content=sample_content,
            report_type="quarterly_report",
            source="sample",
            date="2024-12-31"
        )

        sample_research = f"""
{ticker} 深度研报 - 行业龙头地位稳固

投资亮点：
1. 市场份额持续提升，在主要产品线市场占有率已达 35%
2. 研发投入强度行业领先，技术壁垒不断加深
3. 全球化布局成效显著，海外收入占比已超 40%
4. 现金流充沛，股息支付率稳定在 50%

风险因素：
1. 原材料价格波动可能影响毛利率
2. 汇率变动对海外收入产生不确定性
3. 行业竞争加剧可能带来价格压力

盈利预测：
- 2025 年净利润预计增长 18%
- 2026 年净利润预计增长 15%

投资建议：逢低买入，目标价 180 元。
"""
        self.add_company_research_report(
            ticker=ticker,
            title=f"{ticker} 深度投资研报",
            content=sample_research,
            report_type="research_report",
            source="sample",
            date="2024-11-15"
        )


_knowledge_service_instances: Dict[str, KnowledgeService] = {}
_knowledge_service_lock = threading.Lock()


def create_knowledge_service(
    config: Optional[Dict[str, Any]] = None,
    name: str = "default"
) -> KnowledgeService:
    """
    工厂函数：创建知识服务实例（推荐使用）

    Args:
        config: 配置字典
        name: 实例名称，支持多实例

    Returns:
        KnowledgeService 实例
    """
    with _knowledge_service_lock:
        if name not in _knowledge_service_instances:
            _knowledge_service_instances[name] = KnowledgeService(config=config)
            logger.info(f"📚 创建知识服务实例: {name}")
        return _knowledge_service_instances[name]


def get_knowledge_service(config: Optional[Dict[str, Any]] = None) -> KnowledgeService:
    """
    获取知识服务实例（兼容接口，推荐使用 create_knowledge_service）
    使用线程本地存储，每个线程获得独立实例
    """
    global _thread_local
    try:
        return _thread_local.knowledge_service
    except AttributeError:
        service = create_knowledge_service(config, name="thread_default")
        _thread_local.knowledge_service = service
        return service


def init_knowledge_service(
    vector_store: BaseVectorStore,
    config: Optional[Dict[str, Any]] = None,
    name: str = "default"
) -> KnowledgeService:
    """
    初始化命名知识服务实例

    Args:
        vector_store: 向量存储实例
        config: 配置字典
        name: 实例名称

    Returns:
        KnowledgeService 实例
    """
    with _knowledge_service_lock:
        instance = KnowledgeService(vector_store=vector_store, config=config)
        _knowledge_service_instances[name] = instance
        logger.info(f"📚 初始化知识服务实例: {name}")
        return instance


def clear_knowledge_service(name: Optional[str] = None):
    """
    清理知识服务实例

    Args:
        name: 实例名称，None 表示清理所有
    """
    global _knowledge_service_instances
    with _knowledge_service_lock:
        if name:
            if name in _knowledge_service_instances:
                del _knowledge_service_instances[name]
                logger.info(f"🗑️ 清理知识服务实例: {name}")
        else:
            _knowledge_service_instances.clear()
            logger.info("🗑️ 清理所有知识服务实例")