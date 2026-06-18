"""
投资组合分析图 - 多标的并行分析框架
支持对多个股票同时进行并行分析，并汇总结果
"""
import os
import asyncio
from contextlib import contextmanager
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from tradingagents.utils.logging_init import get_logger

logger = get_logger("portfolio_graph")


@contextmanager
def stock_analysis_context(ticker: str):
    """股票分析资源保护上下文管理器"""
    resources = {"graph": None, "start_time": None}
    try:
        import time
        resources["start_time"] = time.time()
        logger.info(f"🔄 [Portfolio] 开始分析 {ticker}")
        yield resources
    except KeyboardInterrupt:
        logger.warning(f"⚠️ [Portfolio] {ticker} 分析被用户中断")
        raise
    except MemoryError:
        logger.error(f"❌ [Portfolio] {ticker} 分析内存不足")
        raise
    except Exception as e:
        logger.error(f"❌ [Portfolio] {ticker} 分析异常: {e}")
        raise
    finally:
        if resources.get("graph"):
            try:
                del resources["graph"]
            except Exception:
                pass
        if resources.get("start_time"):
            import time
            elapsed = time.time() - resources["start_time"]
            logger.info(f"🏁 [Portfolio] {ticker} 分析完成，耗时: {elapsed:.2f}s")


@dataclass
class StockAnalysisResult:
    """单只股票分析结果"""
    ticker: str
    success: bool
    decision: Optional[Dict[str, Any]] = None
    analysis: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time: float = 0.0


@dataclass
class PortfolioAnalysisResult:
    """投资组合分析结果"""
    tickers: List[str]
    results: List[StockAnalysisResult]
    summary: Dict[str, Any] = field(default_factory=dict)
    execution_time: float = 0.0

    def get_successful_results(self) -> List[StockAnalysisResult]:
        return [r for r in self.results if r.success]

    def get_failed_results(self) -> List[StockAnalysisResult]:
        return [r for r in self.results if not r.success]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tickers": self.tickers,
            "total": len(self.tickers),
            "successful": len(self.get_successful_results()),
            "failed": len(self.get_failed_results()),
            "execution_time": round(self.execution_time, 2),
            "summary": self.summary,
            "results": [
                {
                    "ticker": r.ticker,
                    "success": r.success,
                    "decision": r.decision,
                    "error": r.error,
                    "execution_time": round(r.execution_time, 2)
                }
                for r in self.results
            ]
        }


class PortfolioAnalyzer:
    """
    投资组合并行分析器
    使用多线程对多只股票进行并行分析
    """

    def __init__(
        self,
        trading_graph_class,
        max_workers: int = 5,
        timeout_per_stock: int = 600
    ):
        """
        初始化投资组合分析器

        Args:
            trading_graph_class: TradingAgentsGraph 类或实例
            max_workers: 最大并行数
            timeout_per_stock: 单只股票分析超时时间（秒）
        """
        self.trading_graph_class = trading_graph_class
        self.max_workers = max_workers
        self.timeout_per_stock = timeout_per_stock

    def analyze_single_stock(
        self,
        ticker: str,
        pub_date: str,
        config: Dict[str, Any]
    ) -> StockAnalysisResult:
        """
        分析单只股票（线程安全）
        """
        import time
        start_time = time.time()

        try:
            logger.info(f"🔄 [Portfolio] 开始分析 {ticker}")

            graph_instance = self.trading_graph_class(
                selected_analysts=config.get("selected_analysts", ["market", "fundamentals"]),
                config=config
            )

            result = graph_instance.run(ticker, pub_date)

            execution_time = time.time() - start_time

            if result:
                decision = result.get("decision", {})
                return StockAnalysisResult(
                    ticker=ticker,
                    success=True,
                    decision={
                        "action": decision.get("action"),
                        "target_price": decision.get("target_price"),
                        "confidence": decision.get("confidence"),
                        "reasoning": decision.get("reasoning", "")[:500]
                    },
                    analysis={
                        "bull_view": result.get("bull_view", ""),
                        "bear_view": result.get("bear_view", ""),
                        "risk_assessment": result.get("risk_assessment", "")
                    },
                    execution_time=execution_time
                )
            else:
                return StockAnalysisResult(
                    ticker=ticker,
                    success=False,
                    error="分析未返回结果",
                    execution_time=execution_time
                )

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"❌ [Portfolio] 分析 {ticker} 失败: {e}")
            return StockAnalysisResult(
                ticker=ticker,
                success=False,
                error=str(e),
                execution_time=execution_time
            )

    def analyze_portfolio(
        self,
        tickers: List[str],
        pub_date: str,
        config: Dict[str, Any]
    ) -> PortfolioAnalysisResult:
        """
        并行分析多个股票

        Args:
            tickers: 股票代码列表
            pub_date: 分析日期
            config: 配置字典

        Returns:
            PortfolioAnalysisResult: 投资组合分析结果
        """
        import time
        start_time = time.time()

        logger.info(f"🚀 [Portfolio] 开始并行分析 {len(tickers)} 只股票: {tickers}")

        results: List[StockAnalysisResult] = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_ticker = {
                executor.submit(
                    self.analyze_single_stock,
                    ticker,
                    pub_date,
                    config
                ): ticker
                for ticker in tickers
            }

            for future in as_completed(future_to_ticker, timeout=self.timeout_per_stock * len(tickers)):
                ticker = future_to_ticker[future]
                try:
                    result = future.result()
                    results.append(result)
                    status = "✅" if result.success else "❌"
                    logger.info(f"{status} [Portfolio] {ticker} 分析完成 ({result.execution_time:.1f}s)")
                except Exception as e:
                    logger.error(f"❌ [Portfolio] {ticker} 执行异常: {e}")
                    results.append(StockAnalysisResult(
                        ticker=ticker,
                        success=False,
                        error=str(e)
                    ))

        execution_time = time.time() - start_time
        summary = self._generate_summary(results, config)

        return PortfolioAnalysisResult(
            tickers=tickers,
            results=results,
            summary=summary,
            execution_time=execution_time
        )

    def _generate_summary(
        self,
        results: List[StockAnalysisResult],
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """生成汇总报告"""
        successful = self.get_successful_results()
        failed = self.get_failed_results()

        buy_count = sum(
            1 for r in successful
            if r.decision and r.decision.get("action") == "买入"
        )
        sell_count = sum(
            1 for r in successful
            if r.decision and r.decision.get("action") == "卖出"
        )
        hold_count = sum(
            1 for r in successful
            if r.decision and r.decision.get("action") == "持有"
        )

        avg_confidence = 0.0
        if successful:
            confidences = [
                r.decision.get("confidence", 0)
                for r in successful
                if r.decision and r.decision.get("confidence") is not None
            ]
            if confidences:
                avg_confidence = sum(confidences) / len(confidences)

        return {
            "total_tickers": len(results),
            "successful": len(successful),
            "failed": len(failed),
            "actions": {
                "买入": buy_count,
                "卖出": sell_count,
                "持有": hold_count
            },
            "average_confidence": round(avg_confidence, 3),
            "recommendations": self._generate_recommendations(
                buy_count, sell_count, hold_count, avg_confidence
            )
        }

    def _generate_recommendations(
        self,
        buy_count: int,
        sell_count: int,
        hold_count: int,
        avg_confidence: float
    ) -> str:
        """生成投资建议"""
        if buy_count > hold_count and buy_count > sell_count:
            sentiment = "偏多"
            recommendation = "建议关注买入信号较强的标的"
        elif sell_count > hold_count and sell_count > buy_count:
            sentiment = "偏空"
            recommendation = "建议关注卖出信号较强的标的，注意风险"
        elif hold_count > 0:
            sentiment = "中性"
            recommendation = "市场情绪偏谨慎，建议观望"
        else:
            sentiment = "不确定"
            recommendation = "分析结果不足以给出明确建议"

        confidence_text = "高" if avg_confidence > 0.7 else "中" if avg_confidence > 0.5 else "低"

        return f"整体{sentiment}，Confidence: {confidence_text} ({avg_confidence:.1%})，{recommendation}"


class AsyncPortfolioAnalyzer:
    """
    异步投资组合分析器
    使用 asyncio 对多只股票进行并行分析
    """

    def __init__(
        self,
        trading_graph_class,
        max_workers: int = 5,
        timeout_per_stock: int = 600
    ):
        self.trading_graph_class = trading_graph_class
        self.max_workers = max_workers
        self.timeout_per_stock = timeout_per_stock

    async def analyze_portfolio_async(
        self,
        tickers: List[str],
        pub_date: str,
        config: Dict[str, Any]
    ) -> PortfolioAnalysisResult:
        """异步并行分析多个股票"""
        import time
        start_time = time.time()

        logger.info(f"🚀 [AsyncPortfolio] 开始异步并行分析 {len(tickers)} 只股票")

        semaphore = asyncio.Semaphore(self.max_workers)

        async def analyze_with_semaphore(ticker: str) -> StockAnalysisResult:
            async with semaphore:
                return await asyncio.to_thread(
                    self._analyze_stock_sync,
                    ticker,
                    pub_date,
                    config
                )

        tasks = [analyze_with_semaphore(ticker) for ticker in tickers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(StockAnalysisResult(
                    ticker=tickers[i],
                    success=False,
                    error=str(result)
                ))
            else:
                processed_results.append(result)

        execution_time = time.time() - start_time
        portfolio_result = PortfolioAnalyzer(
            self.trading_graph_class,
            self.max_workers,
            self.timeout_per_stock
        )
        summary = portfolio_result._generate_summary(processed_results, config)

        return PortfolioAnalysisResult(
            tickers=tickers,
            results=processed_results,
            summary=summary,
            execution_time=execution_time
        )

    def _analyze_stock_sync(
        self,
        ticker: str,
        pub_date: str,
        config: Dict[str, Any]
    ) -> StockAnalysisResult:
        """同步分析单只股票（供线程调用）"""
        import time
        start_time = time.time()

        try:
            logger.info(f"🔄 [AsyncPortfolio] 开始分析 {ticker}")

            graph_instance = self.trading_graph_class(
                selected_analysts=config.get("selected_analysts", ["market", "fundamentals"]),
                config=config
            )

            result = graph_instance.run(ticker, pub_date)
            execution_time = time.time() - start_time

            if result:
                decision = result.get("decision", {})
                return StockAnalysisResult(
                    ticker=ticker,
                    success=True,
                    decision=decision,
                    execution_time=execution_time
                )
            else:
                return StockAnalysisResult(
                    ticker=ticker,
                    success=False,
                    error="分析未返回结果",
                    execution_time=execution_time
                )

        except Exception as e:
            execution_time = time.time() - start_time
            return StockAnalysisResult(
                ticker=ticker,
                success=False,
                error=str(e),
                execution_time=execution_time
            )


def quick_portfolio_analysis(
    trading_graph_class,
    tickers: List[str],
    pub_date: str,
    config: Dict[str, Any],
    max_workers: int = 5
) -> PortfolioAnalysisResult:
    """
    快速投资组合分析（简化接口）

    Args:
        trading_graph_class: TradingAgentsGraph 类
        tickers: 股票代码列表
        pub_date: 分析日期
        config: 配置字典
        max_workers: 最大并行数

    Returns:
        PortfolioAnalysisResult: 投资组合分析结果

    Example:
        result = quick_portfolio_analysis(
            TradingAgentsGraph,
            ["AAPL", "MSFT", "GOOGL"],
            "2024-01-15",
            {"deep_think_llm_provider": "openai", ...}
        )
        print(result.summary)
    """
    analyzer = PortfolioAnalyzer(
        trading_graph_class=trading_graph_class,
        max_workers=max_workers
    )

    return analyzer.analyze_portfolio(
        tickers=tickers,
        pub_date=pub_date,
        config=config
    )