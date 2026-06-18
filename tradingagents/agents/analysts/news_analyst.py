from tradingagents.agents.utils.agent_utils import create_analyst_node
from tradingagents.config.prompts import NEWS_OUTPUT_FORMAT

def create_news_analyst(llm, toolkit):
    """
    创建新闻分析师节点。
    """
    tools = [toolkit.get_stock_news_unified]
    
    return create_analyst_node(
        llm=llm,
        analyst_type="新闻",
        output_format=NEWS_OUTPUT_FORMAT,
        tools=tools,
        special_requirements="重点关注最新新闻动态、重大事件影响以及市场关注点。"
    )
