from tradingagents.agents.utils.agent_utils import create_analyst_node
from tradingagents.config.prompts import SENTIMENT_OUTPUT_FORMAT

def create_social_media_analyst(llm, toolkit):
    """
    创建社交媒体情绪分析师节点。
    """
    tools = [toolkit.get_stock_sentiment_unified]
    
    return create_analyst_node(
        llm=llm,
        analyst_type="情绪",
        output_format=SENTIMENT_OUTPUT_FORMAT,
        tools=tools,
        special_requirements="重点关注社交媒体上的投资者情绪、讨论热度以及看多/看空观点。"
    )
