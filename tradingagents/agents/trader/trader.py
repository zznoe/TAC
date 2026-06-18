import functools
import time
import json

# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger
from tradingagents.agents.utils.instrument_utils import build_instrument_context
logger = get_logger("default")


def create_trader(llm, memory):
    def trader_node(state, name):
        company_name = state["company_of_interest"]
        instrument_context = build_instrument_context(company_name)
        investment_plan = state["investment_plan"]
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        # 使用统一的股票类型检测
        from tradingagents.utils.stock_utils import StockUtils
        market_info = StockUtils.get_market_info(company_name)
        is_china = market_info['is_china']
        is_hk = market_info['is_hk']
        is_us = market_info['is_us']

        # 根据股票类型确定货币单位
        currency = market_info['currency_name']
        currency_symbol = market_info['currency_symbol']

        logger.debug(f"💰 [DEBUG] ===== 交易员节点开始 =====")
        logger.debug(f"💰 [DEBUG] 交易员检测股票类型: {company_name} -> {market_info['market_name']}, 货币: {currency}")
        logger.debug(f"💰 [DEBUG] 货币符号: {currency_symbol}")
        logger.debug(f"💰 [DEBUG] 市场详情: 中国A股={is_china}, 港股={is_hk}, 美股={is_us}")
        logger.debug(f"💰 [DEBUG] 基本面报告长度: {len(fundamentals_report)}")
        logger.debug(f"💰 [DEBUG] 基本面报告前200字符: {fundamentals_report[:200]}...")

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"

        # 检查memory是否可用
        if memory is not None:
            logger.warning(f"⚠️ [DEBUG] memory可用，获取历史记忆")
            past_memories = memory.get_memories(curr_situation, n_matches=2)
            past_memory_str = ""
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec["recommendation"] + "\n\n"
        else:
            logger.warning(f"⚠️ [DEBUG] memory为None，跳过历史记忆检索")
            past_memories = []
            past_memory_str = "暂无历史记忆数据可参考。"

        context = {
            "role": "user",
            "content": f"Based on a comprehensive analysis by a team of analysts, here is an investment plan tailored for {company_name}. This plan incorporates insights from current technical market trends, macroeconomic indicators, and social media sentiment. Use this plan as a foundation for evaluating your next trading decision.\n\nProposed Investment Plan: {investment_plan}\n\nLeverage these insights to make an informed and strategic decision.",
        }

        from tradingagents.config.prompts import TRADER_SYSTEM_PROMPT
        
        system_prompt = TRADER_SYSTEM_PROMPT.format(
            company_name=company_name,
            currency=currency,
            currency_symbol=currency_symbol,
            instrument_context=instrument_context,
            past_memory_str=past_memory_str
        )

        messages = [
            {
                "role": "system",
                "content": system_prompt,
            },
            context,
        ]

        from tradingagents.agents.utils.agent_states import TraderPlan

        logger.debug(f"💰 [DEBUG] 准备调用LLM，系统提示包含货币: {currency}")
        logger.debug(f"💰 [DEBUG] 系统提示中的关键部分: 目标价格({currency})")

        structured_llm = llm.with_structured_output(TraderPlan)
        response = structured_llm.invoke(messages)
        response_json = response.model_dump_json()

        logger.debug(f"💰 [DEBUG] LLM调用完成")
        logger.debug(f"💰 [DEBUG] 交易员回复内容: {response_json}")
        logger.debug(f"💰 [DEBUG] ===== 交易员节点结束 =====")

        # 构造一条兼容的AIMessage，因为某些图节点可能会读取 messages
        from langchain_core.messages import AIMessage
        ai_msg = AIMessage(content=response_json, name=name)

        return {
            "messages": [ai_msg],
            "trader_investment_plan": response_json,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
