from tradingagents.agents.utils.agent_utils import create_analyst_node
from tradingagents.config.prompts import MARKET_OUTPUT_FORMAT

def create_market_analyst(llm, toolkit):
    """
    创建市场分析师节点。
    """
    tools = [toolkit.get_stock_market_data_unified]
    
    return create_analyst_node(
        llm=llm,
        analyst_type="市场",
        output_format=MARKET_OUTPUT_FORMAT,
        tools=tools,
        special_requirements="重点关注技术指标分析（MA, MACD, RSI, BOLL）和价格趋势。"
    )
