import time
import json
import re

# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger
from tradingagents.agents.utils.instrument_utils import build_instrument_context
from tradingagents.agents.utils.agent_states import InvestmentDecision
logger = get_logger("default")

class QuantitativeRiskEngine:
    """传统量化风控引擎：双轨制风控的硬性规则层"""
    
    @staticmethod
    def evaluate(trader_plan_json: str, market_report: str) -> dict:
        """
        评估交易计划，执行硬性风控规则。
        """
        logger.info("🛡️ [Quant Risk Engine] 执行量化风控规则检查...")
        
        try:
            plan_data = json.loads(trader_plan_json)
            action = plan_data.get("action", "")
            target_price = plan_data.get("target_price")
            
            # 规则 1：极端风险关键词拦截
            risk_keywords = ["熔断", "跌停潮", "系统性风险", "极端恐慌"]
            for kw in risk_keywords:
                if kw in market_report:
                    logger.warning(f"🚨 [Quant Risk Engine] 触发硬性拦截：市场报告包含风险关键词 '{kw}'")
                    return {
                        "triggered": True,
                        "action": "持有",
                        "reasoning": f"量化风控检测到市场存在'{kw}'等极端风险指标，触发强制持有观望机制。"
                    }
            
            # 规则 2：非理性的预期收益率拦截
            # 如果是买入建议，且目标价远高于当前（需要当前价数据，此处简化）
            # 这里暂时只检查目标价是否存在
            if action == "买入" and target_price is None:
                logger.warning("🚨 [Quant Risk Engine] 触发硬性拦截：买入决策缺少目标价位")
                return {
                    "triggered": True,
                    "action": "持有",
                    "reasoning": "买入决策必须包含具体的目标价位，当前计划不符合风控要求。"
                }

        except Exception as e:
            logger.error(f"⚠️ [Quant Risk Engine] 解析交易计划失败: {e}")
            
        return {"triggered": False}

def create_risk_manager(llm, memory):
    def risk_manager_node(state) -> dict:

        company_name = state["company_of_interest"]
        instrument_context = build_instrument_context(company_name)

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        market_research_report = state["market_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        sentiment_report = state["sentiment_report"]
        trader_plan = state.get("trader_investment_plan", "")

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        
        # --- 1. 双轨制风控：先执行传统量化风控规则 ---
        quant_result = QuantitativeRiskEngine.evaluate(trader_plan, market_research_report)
        if quant_result["triggered"]:
            # 触发硬性拦截，LLM 仅用于解释
            logger.warning("🛡️ [Risk Manager] 量化规则生效，直接生成风控决策")
            decision = InvestmentDecision(
                action=quant_result["action"],
                target_price=None,
                confidence=0.9,
                risk_score=0.9,
                reasoning=quant_result["reasoning"] + "\n\n(AI 解释：在极端市场条件下，量化模型自动熔断了该交易计划以保护本金。)"
            )
            response_content = decision.model_dump_json()
            
            new_risk_debate_state = {
                "judge_decision": response_content,
                "history": risk_debate_state["history"],
                "risky_history": risk_debate_state["risky_history"],
                "safe_history": risk_debate_state["safe_history"],
                "neutral_history": risk_debate_state["neutral_history"],
                "latest_speaker": "Judge",
                "current_risky_response": risk_debate_state["current_risky_response"],
                "current_safe_response": risk_debate_state["current_safe_response"],
                "current_neutral_response": risk_debate_state["current_neutral_response"],
                "count": risk_debate_state["count"],
            }
            return {
                "risk_debate_state": new_risk_debate_state,
                "final_trade_decision": response_content,
            }

        # --- 2. 大模型风控：执行多智能体辩论评估 ---

        # 安全检查：确保memory不为None
        if memory is not None:
            past_memories = memory.get_memories(curr_situation, n_matches=2)
        else:
            logger.warning(f"⚠️ [DEBUG] memory为None，跳过历史记忆检索")
            past_memories = []

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""作为风险管理委员会主席和辩论主持人，您的目标是评估三位风险分析师——激进、中性和安全/保守——之间的辩论，并确定交易员的最佳行动方案。您的决策必须产生明确的建议：买入、卖出或持有。只有在有具体论据强烈支持时才选择持有，而不是在所有方面都似乎有效时作为后备选择。力求清晰和果断。

决策指导原则：
1. **总结关键论点**：提取每位分析师的最强观点，重点关注与背景的相关性。
2. **提供理由**：用辩论中的直接引用和反驳论点支持您的建议。
3. **完善交易员计划**：从交易员的原始计划**{trader_plan}**开始，根据分析师的见解进行调整。
4. **从过去的错误中学习**：使用**{past_memory_str}**中的经验教训来解决先前的误判，改进您现在做出的决策，确保您不会做出错误的买入/卖出/持有决定而亏损。

交付成果：
- 明确且可操作的建议：买入、卖出或持有。
- 基于辩论和过去反思的详细推理。

标的约束：
{instrument_context}

---

**分析师辩论历史：**
{history}

---

专注于可操作的见解和持续改进。建立在过去经验教训的基础上，批判性地评估所有观点，确保每个决策都能带来更好的结果。请用中文撰写所有分析内容和建议。"""

        # 📊 统计 prompt 大小
        prompt_length = len(prompt)
        # 粗略估算 token 数量（中文约 1.5-2 字符/token，英文约 4 字符/token）
        estimated_tokens = int(prompt_length / 1.8)  # 保守估计

        logger.info(f"📊 [Risk Manager] Prompt 统计:")
        logger.info(f"   - 辩论历史长度: {len(history)} 字符")
        logger.info(f"   - 交易员计划长度: {len(trader_plan)} 字符")
        logger.info(f"   - 历史记忆长度: {len(past_memory_str)} 字符")
        logger.info(f"   - 总 Prompt 长度: {prompt_length} 字符")
        logger.info(f"   - 估算输入 Token: ~{estimated_tokens} tokens")

        # 增强的LLM调用，包含错误处理和重试机制
        from tradingagents.agents.utils.agent_states import InvestmentDecision
        
        max_retries = 3
        retry_count = 0
        response_content = ""

        while retry_count < max_retries:
            try:
                logger.info(f"🔄 [Risk Manager] 调用LLM生成交易决策 (尝试 {retry_count + 1}/{max_retries})")

                # ⏱️ 记录开始时间
                start_time = time.time()

                structured_llm = llm.with_structured_output(InvestmentDecision)
                response = structured_llm.invoke(prompt)

                # ⏱️ 记录结束时间
                elapsed_time = time.time() - start_time
                
                if response:
                    response_content = response.model_dump_json()

                    logger.info(f"⏱️ [Risk Manager] LLM调用耗时: {elapsed_time:.2f}秒")
                    logger.info(f"📊 [Risk Manager] 响应输出: {response_content}")

                    logger.info(f"✅ [Risk Manager] LLM调用成功")
                    break
                else:
                    logger.warning(f"⚠️ [Risk Manager] LLM响应为空或无效")
                    response_content = ""

            except Exception as e:
                elapsed_time = time.time() - start_time
                logger.error(f"❌ [Risk Manager] LLM调用失败 (尝试 {retry_count + 1}): {str(e)}")
                logger.error(f"⏱️ [Risk Manager] 失败前耗时: {elapsed_time:.2f}秒")
                response_content = ""
            
            retry_count += 1
            if retry_count < max_retries and not response_content:
                logger.info(f"🔄 [Risk Manager] 等待2秒后重试...")
                time.sleep(2)
        
        # 如果所有重试都失败，生成默认决策
        if not response_content:
            logger.error(f"❌ [Risk Manager] 所有LLM调用尝试失败，使用默认决策")
            default_decision = InvestmentDecision(
                action="持有",
                target_price=None,
                confidence=0.5,
                risk_score=0.5,
                reasoning=f"由于技术原因无法生成详细分析，基于当前市场状况和风险控制原则，建议对{company_name}采取持有策略。"
            )
            response_content = default_decision.model_dump_json()

        new_risk_debate_state = {
            "judge_decision": response_content,
            "history": risk_debate_state["history"],
            "risky_history": risk_debate_state["risky_history"],
            "safe_history": risk_debate_state["safe_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_risky_response": risk_debate_state["current_risky_response"],
            "current_safe_response": risk_debate_state["current_safe_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        logger.info(f"📋 [Risk Manager] 最终决策生成完成，内容长度: {len(response_content)} 字符")
        
        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": response_content,
        }

    return risk_manager_node
