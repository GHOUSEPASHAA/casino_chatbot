import os
import json
from pathlib import Path
from typing import Annotated, Sequence, TypedDict
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from snowdb import db, get_gold_objects

load_dotenv()

# --------------------------------------------------
# 1. Prompt File Loader Utility
# --------------------------------------------------
PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(filename: str, **kwargs) -> str:
    """Reads a template file from the prompts directory and formats variables."""
    template_path = PROMPTS_DIR / filename
    if not template_path.exists():
        raise FileNotFoundError(f"Prompt template file not found at: {template_path}")
    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()
    return content.format(**kwargs) if kwargs else content


# --------------------------------------------------
# 2. Initialize Azure OpenAI LLM
# --------------------------------------------------
llm = ChatOpenAI(
    model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    base_url=os.environ["AZURE_OPENAI_BASEURL"],
    temperature=0,
)

# --------------------------------------------------
# 3. Database Metadata & Tools Setup
# --------------------------------------------------
database = os.getenv("SNOWFLAKE_DATABASE")
schema = os.getenv("SNOWFLAKE_SCHEMA", "GOLD")

toolkit = SQLDatabaseToolkit(db=db, llm=llm)
tools = toolkit.get_tools()
tool_node = ToolNode(tools)

gold_objects = get_gold_objects()
gold_objects_text = "\n".join(f"- {database}.{schema}.{name}" for name in gold_objects)


# --------------------------------------------------
# 4. Agent State Definition
# --------------------------------------------------
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    intent: str
    domain: str


# --------------------------------------------------
# 5. Agent Workflow Nodes
# --------------------------------------------------
def preflight_router_node(state: AgentState):
    """Classifies user intent and routes to the appropriate business domain."""
    human_messages = [m for m in state["messages"] if m.type == "human"]
    last_user_msg = human_messages[-1].content if human_messages else ""

    router_prompt = load_prompt("router.txt")

    response = llm.invoke([
        SystemMessage(content=router_prompt),
        HumanMessage(content=last_user_msg)
    ])

    try:
        cleaned = response.content.strip().strip("```json").strip("```")
        parsed = json.loads(cleaned)
        intent = parsed.get("intent", "ANALYTICS")
        domain = parsed.get("domain", "GENERAL")
    except Exception:
        intent = "ANALYTICS"
        domain = "GENERAL"

    return {"intent": intent, "domain": domain}

def generate_sql_node(state: AgentState):
    """Loads sql_generation.txt, injects domain context, and calls tools."""
    domain = state.get("domain", "GENERAL")

    domain_routing_map = {
        "SPA": "Use vw_llm_timeseries_spa for revenue/trends and vw_llm_facttimeseries_spa_detail for transaction-level details.",
        "HOTEL": "Use vw_llm_hotel_stays for stays/nights/reservations and vw_llm_timeseries_hotel for revenue trends.",
        "POS": "Use vw_llm_timeseries_pos for food/retail spending and vw_llm_facttimeseries_pos_detail for itemized receipts.",
        "GAMING": "Use vw_llm_timeseries_gaming for player gaming activity/turnover and vw_llm_game_profile for game info.",
        "CUSTOMER": "Use vw_llm_person_profile for customer demographic details.",
        "HOST": "Use vw_llm_host_profile for casino hosts and host assignment performance.",
        "CAMPAIGN": "Use vw_llm_campaign_profile for marketing campaign analytics.",
        "OFFER": "Use vw_llm_offer_profile for promotional performance.",
        "PROPERTY": "Use vw_llm_dim_property for casino property and resort details.",
        "GENERAL": "Use app_entity_search for discovery or vw_llm_facttimeseries when no domain view applies."
    }
    selected_rule = domain_routing_map.get(domain, domain_routing_map["GENERAL"])

    # Must match the exact placeholders in your sql_generation.txt template:
    # {database}, {schema}, {domain}, {domain_guidelines}, {tables_info}
    system_instruction = load_prompt(
        "sql_generation.txt",
        database=database,
        schema=schema,
        domain=domain,
        domain_guidelines=selected_rule,
        tables_info=gold_objects_text
    )

    llm_with_tools = llm.bind_tools(tools)
    conversation = [SystemMessage(content=system_instruction)] + list(state["messages"])
    
    response = llm_with_tools.invoke(conversation)
    return {"messages": [response]}

    llm_with_tools = llm.bind_tools(tools)
    conversation = [SystemMessage(content=system_instruction)] + list(state["messages"])
    
    response = llm_with_tools.invoke(conversation)
    return {"messages": [response]}


def general_responder_node(state: AgentState):
    """Handles conversational greetings or queries requiring clarification."""
    intent = state.get("intent", "GREETING")
    if intent == "GREETING":
        msg = (
            "Hello! I am your Casino Data Analytics Assistant. "
            "You can ask me questions about Hotel stays, SPA revenue, "
            "Gaming performance, POS dining receipts, or Customer profiles."
        )
    else:
        msg = (
            "I could not determine the exact data domain you want to analyze. "
            "Could you please specify whether you are looking for Hotel, SPA, "
            "POS, or Gaming metrics, along with any relevant time period?"
        )
    return {"messages": [AIMessage(content=msg)]}


def synthesize_answer_node(state: AgentState):
    """Translates SQL tool execution output into a formatted natural language response."""
    synthesis_instruction = load_prompt("synthesize.txt")
    response = llm.invoke([SystemMessage(content=synthesis_instruction)] + list(state["messages"]))
    return {"messages": [response]}


# --------------------------------------------------
# 6. Conditional Routing Edges
# --------------------------------------------------
def route_intent_edge(state: AgentState):
    if state.get("intent") == "ANALYTICS":
        return "generate_sql"
    return "general_responder"


def should_continue_tools_edge(state: AgentState):
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "synthesize"


# --------------------------------------------------
# 7. Workflow Graph Assembly
# --------------------------------------------------
workflow = StateGraph(AgentState)

# Add processing nodes
workflow.add_node("preflight_router", preflight_router_node)
workflow.add_node("generate_sql", generate_sql_node)
workflow.add_node("tools", tool_node)
workflow.add_node("synthesize", synthesize_answer_node)
workflow.add_node("general_responder", general_responder_node)

workflow.set_entry_point("preflight_router")

# Routing edges
workflow.add_conditional_edges(
    "preflight_router",
    route_intent_edge,
    {
        "generate_sql": "generate_sql",
        "general_responder": "general_responder",
    }
)

workflow.add_conditional_edges(
    "generate_sql",
    should_continue_tools_edge,
    {
        "tools": "tools",
        "synthesize": "synthesize",
    }
)

workflow.add_edge("tools", "generate_sql")
workflow.add_edge("synthesize", END)
workflow.add_edge("general_responder", END)

# In-memory checkpointer provides multi-turn thread support
memory = MemorySaver()
graph = workflow.compile(checkpointer=memory)


# --------------------------------------------------
# 8. Standalone Execution Helper
# --------------------------------------------------
def ask_database(question: str, thread_id: str = "default_thread") -> str:
    """Helper function to execute queries synchronously outside of Chainlit."""
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(
        {"messages": [HumanMessage(content=question)]},
        config=config
    )

    for msg in reversed(result["messages"]):
        if getattr(msg, "type", None) == "ai" and msg.content:
            return msg.content

    return "I could not generate an answer."