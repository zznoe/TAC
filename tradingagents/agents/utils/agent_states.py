from typing import Annotated, Sequence
from datetime import date, timedelta, datetime
from typing_extensions import TypedDict, Optional
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import ToolNode
from langgraph.graph import END, StateGraph, START, MessagesState

# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")

from typing import List, Dict, Any
from langchain_core.messages import BaseMessage
import operator
from pydantic import BaseModel, Field, field_validator, model_validator

# --- Pydantic Models for Structured Output ---

VALID_ACTIONS = {"买入", "卖出", "持有", "Buy", "Sell", "Hold", "buy", "sell", "hold"}

class InvestmentDecision(BaseModel):
    action: str = Field(description="Action to take: 买入 (Buy), 卖出 (Sell), or 持有 (Hold)")
    target_price: Optional[float] = Field(default=None, description="Target price for the asset")
    stop_loss: Optional[float] = Field(default=None, description="Stop loss price")
    confidence: float = Field(default=0.7, description="Confidence level between 0 and 1", ge=0.0, le=1.0)
    risk_score: float = Field(default=0.5, description="Risk score between 0 and 1", ge=0.0, le=1.0)
    reasoning: str = Field(description="Detailed reasoning for the decision")

    @field_validator('action')
    @classmethod
    def validate_action(cls, v: str) -> str:
        v = v.strip()
        if v not in VALID_ACTIONS:
            raise ValueError(f"Invalid action: {v}. Must be one of: {VALID_ACTIONS}")
        return v

    @field_validator('target_price', 'stop_loss')
    @classmethod
    def validate_positive_price(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError(f"Price must be positive: {v}")
        return v

    @model_validator(mode='after')
    def validate_consistency(self):
        if self.target_price is not None and self.stop_loss is not None:
            if self.action == "买入" and self.stop_loss >= self.target_price:
                raise ValueError("Stop loss should be less than target price for BUY action")
            if self.action == "卖出" and self.stop_loss <= self.target_price:
                raise ValueError("Stop loss should be greater than target price for SELL action")
        return self

class TraderPlan(BaseModel):
    action: str = Field(description="Action to take: 买入, 卖出, or 持有")
    target_price: Optional[float] = Field(default=None, description="Target price for the asset")
    position_size: Optional[str] = Field(default=None, description="Suggested position size or allocation percentage")
    reasoning: str = Field(description="Detailed trading execution plan and reasoning")

    @field_validator('action')
    @classmethod
    def validate_action(cls, v: str) -> str:
        v = v.strip()
        if v not in VALID_ACTIONS:
            raise ValueError(f"Invalid action: {v}. Must be one of: {VALID_ACTIONS}")
        return v

    @field_validator('target_price')
    @classmethod
    def validate_positive_price(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError(f"Target price must be positive: {v}")
        return v

# --- LangGraph State Definitions ---

# Researcher team state
class InvestDebateState(TypedDict):
    bull_history: Annotated[
        str, "Bullish Conversation history"
    ]  # Bullish Conversation history
    bear_history: Annotated[
        str, "Bearish Conversation history"
    ]  # Bullish Conversation history
    history: Annotated[str, "Conversation history"]  # Conversation history
    current_response: Annotated[str, "Latest response"]  # Last response
    judge_decision: Annotated[str, "Final judge decision"]  # Last response
    count: Annotated[int, "Length of the current conversation"]  # Conversation length


# Risk management team state
class RiskDebateState(TypedDict):
    risky_history: Annotated[
        str, "Risky Agent's Conversation history"
    ]  # Conversation history
    safe_history: Annotated[
        str, "Safe Agent's Conversation history"
    ]  # Conversation history
    neutral_history: Annotated[
        str, "Neutral Agent's Conversation history"
    ]  # Conversation history
    history: Annotated[str, "Conversation history"]  # Conversation history
    latest_speaker: Annotated[str, "Analyst that spoke last"]
    current_risky_response: Annotated[
        str, "Latest response by the risky analyst"
    ]  # Last response
    current_safe_response: Annotated[
        str, "Latest response by the safe analyst"
    ]  # Last response
    current_neutral_response: Annotated[
        str, "Latest response by the neutral analyst"
    ]  # Last response
    judge_decision: Annotated[str, "Judge's decision"]
    count: Annotated[int, "Length of the current conversation"]  # Conversation length


class AgentState(MessagesState):
    company_of_interest: Annotated[str, "Company that we are interested in trading"]
    trade_date: Annotated[str, "What date we are trading at"]

    sender: Annotated[str, "Agent that sent this message"]

    # research step
    market_report: Annotated[str, "Report from the Market Analyst"]
    sentiment_report: Annotated[str, "Report from the Social Media Analyst"]
    news_report: Annotated[
        str, "Report from the News Researcher of current world affairs"
    ]
    fundamentals_report: Annotated[str, "Report from the Fundamentals Researcher"]

    # 🔧 死循环修复: 工具调用计数器
    market_tool_call_count: Annotated[int, "Market analyst tool call counter"]
    news_tool_call_count: Annotated[int, "News analyst tool call counter"]
    sentiment_tool_call_count: Annotated[int, "Social media analyst tool call counter"]
    fundamentals_tool_call_count: Annotated[int, "Fundamentals analyst tool call counter"]

    # researcher team discussion step
    investment_debate_state: Annotated[
        InvestDebateState, "Current state of the debate on if to invest or not"
    ]
    investment_plan: Annotated[str, "Plan generated by the Analyst"]

    trader_investment_plan: Annotated[str, "Plan generated by the Trader"]

    # risk management team discussion step
    risk_debate_state: Annotated[
        RiskDebateState, "Current state of the debate on evaluating risk"
    ]
    final_trade_decision: Annotated[str, "Final decision made by the Risk Analysts"]
