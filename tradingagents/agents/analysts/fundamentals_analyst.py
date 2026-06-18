from tradingagents.agents.utils.agent_utils import create_analyst_node
from tradingagents.config.prompts import FUNDAMENTALS_OUTPUT_FORMAT

def create_fundamentals_analyst(llm, toolkit):
    """
    创建基本面分析师节点。
    """
    tools = [toolkit.get_stock_fundamentals_unified, toolkit.search_company_documents_rag]
    
    return create_analyst_node(
        llm=llm,
        analyst_type="基本面",
        output_format=FUNDAMENTALS_OUTPUT_FORMAT,
        tools=tools,
        special_requirements="重点关注财务报表、估值倍数（PE/PB/PEG）以及公司的竞争优势。"
    )
