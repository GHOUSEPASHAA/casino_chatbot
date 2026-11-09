
import os
from typing import Annotated, Sequence, TypedDict
from pathlib import Path

from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    BaseMessage,
    SystemMessage,
    HumanMessage
)
from langchain_community.agent_toolkits import SQLDatabaseToolkit

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.runnables import RunnableConfig
from sqlalchemy import text
from snowdb import engine
from snowdb import db

load_dotenv()

# --------------------------------------------------
# 1. Prompt Loader
# --------------------------------------------------

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(filename):
    path = PROMPTS_DIR / filename

    if not path.exists():
        raise FileNotFoundError(path)

    return path.read_text(encoding="utf-8")


# --------------------------------------------------
# 2. Azure OpenAI
# --------------------------------------------------

llm = ChatOpenAI(
    model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    base_url=os.environ["AZURE_OPENAI_BASEURL"],
    temperature=0
)


# --------------------------------------------------
# 3. Database Tools
# --------------------------------------------------

toolkit = SQLDatabaseToolkit(
    db=db,
    llm=llm
)

tools = toolkit.get_tools()

tool_node = ToolNode(tools)


# --------------------------------------------------
# 4. Agent State
# --------------------------------------------------

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]




def set_snowflake_session_user(user_id: str):
    """Sets the session variable in Snowflake for RLS enforcement."""
    if not user_id:
        return
    with engine.connect() as conn:
        conn.execute(
            text("SET CURRENT_APP_USER = :user_id"),
            {"user_id": user_id}
        )

        
# --------------------------------------------------
# 5. SQL Generation
# --------------------------------------------------

def generate_sql_node(state: AgentState, config: RunnableConfig):
    user_id = config.get("configurable", {}).get("user_id")

    # Set Snowflake session variable for RLS
    if user_id:
        with engine.connect() as conn:
            conn.execute(
                text("SET CURRENT_APP_USER = :user_id"),
                {"user_id": str(user_id)}
            )

    system_prompt = load_prompt("sql_generation.txt")

    llm_with_tools = llm.bind_tools(tools)

    response = llm_with_tools.invoke(
        [
            SystemMessage(content=system_prompt)
        ] + list(state["messages"])
    )

    return {
        "messages": [response]
    }


# --------------------------------------------------
# 6. Answer Synthesis
# --------------------------------------------------

def synthesize_answer_node(state: AgentState):

    synthesis_prompt = load_prompt("synthesize.txt")

    response = llm.invoke(
        [
            SystemMessage(content=synthesis_prompt)
        ] + list(state["messages"])
    )

    print("\n========== SYNTHESIS DEBUG ==========", flush=True)
    print("CONTENT TYPE:", type(response.content).__name__, flush=True)
    print("CONTENT:", repr(response.content), flush=True)
    print("=====================================\n", flush=True)

    return {
        "messages": [response]
    }


# --------------------------------------------------
# 7. Tool Routing
# --------------------------------------------------

def should_continue_tools_edge(state: AgentState):

    last_message = state["messages"][-1]

    if getattr(last_message, "tool_calls", None):
        return "tools"

    return "synthesize"


# --------------------------------------------------
# 8. Build Graph
# --------------------------------------------------

workflow = StateGraph(AgentState)

workflow.add_node("generate_sql", generate_sql_node)
workflow.add_node("tools", tool_node)
workflow.add_node("synthesize", synthesize_answer_node)

workflow.set_entry_point("generate_sql")

workflow.add_conditional_edges(
    "generate_sql",
    should_continue_tools_edge,
    {
        "tools": "tools",
        "synthesize": "synthesize"
    }
)

workflow.add_edge("tools", "generate_sql")
workflow.add_edge("synthesize", END)


# --------------------------------------------------
# 9. Memory
# --------------------------------------------------

memory = MemorySaver()

graph = workflow.compile(
    checkpointer=memory
)


# --------------------------------------------------
# 10. Execute
# --------------------------------------------------

def ask_database(question: str, thread_id: str):

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    result = graph.invoke(
        {
            "messages": [
                HumanMessage(content=question)
            ]
        },
        config=config
    )

    for msg in reversed(result["messages"]):

        if msg.type == "ai" and msg.content:
            return msg.content

    return "I could not generate an answer."
