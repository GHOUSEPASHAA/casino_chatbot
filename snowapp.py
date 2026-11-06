import chainlit as cl
from chainlit.types import ThreadDict
from langchain_core.messages import HumanMessage

from auth import authenticate_user
from snowagent import graph
from snowflake_datalayer import SnowflakeDataLayer


# --------------------------------------------------
# 1. Register Data Layer
# --------------------------------------------------
@cl.data_layer
def get_data_layer():
    return SnowflakeDataLayer()


# --------------------------------------------------
# 2. Authentication Callback
# --------------------------------------------------
@cl.password_auth_callback
async def password_auth_callback(username: str, password: str):
    user_data = authenticate_user(username, password)

    if not user_data:
        return None

    return cl.User(
        identifier=str(user_data["user_id"]),
        metadata={
            "email": user_data["email"],
            "full_name": user_data["full_name"],
            "role": user_data["role"],
            "tenant_id": user_data["tenant_id"],
        },
    )


# --------------------------------------------------
# 3. New Chat Session
# --------------------------------------------------
@cl.on_chat_start
async def on_chat_start():
    # Bind session to Chainlit's persistent thread_id
    thread_id = cl.context.session.thread_id or cl.context.session.id
    cl.user_session.set("thread_id", thread_id)

    welcome = """
# Welcome to Medical Test Results Assistant! 🩺

I'm your AI-powered medical test results assistant.

I can help you explore, understand, and analyze your
medical test results using natural language.

## What can you explore?

### 🧪 Test Results
- Show my latest test results.
- Which tests have failed?
- Show all my test reports.
- What are my abnormal test results?

### 📊 Test Analysis
- Which test has the highest deviation?
- Identify tests with drastic changes.
- Show tests with abnormal values.
- Summarize my test results.

### 📈 Trends & Comparisons
- Compare my latest and previous test results.
- Which test values have increased?
- Which test values have decreased?
- Show my test history over time.

### 🔍 Test Report Insights
- Give me a summary of my latest report.
- Highlight important changes in my results.
- Which results require attention?

---

**Start by asking a question about your test results!**

*Note: This assistant provides information about recorded test
results and is not a substitute for professional medical advice.*
"""
    await cl.Message(content=welcome).send()


# --------------------------------------------------
# 4. Resume Historical Chat (Sidebar Click)
# --------------------------------------------------
@cl.on_chat_resume
async def on_chat_resume(thread: ThreadDict):
    # Set the resumed thread ID into session for subsequent LangGraph calls
    cl.user_session.set("thread_id", thread["id"])


# --------------------------------------------------
# 5. Message Execution
# --------------------------------------------------
@cl.on_message
async def on_message(message: cl.Message):
    thread_id = cl.user_session.get("thread_id", cl.context.session.id)
    config = {"configurable": {"thread_id": thread_id}}

    state_input = {
        "messages": [HumanMessage(content=message.content)]
    }

    final_response = cl.Message(content="")
    current_step = None

    try:
        async for event in graph.astream_events(state_input, config=config, version="v2"):
            kind = event["event"]

            # Visual indicator when a tool starts executing
            if kind == "on_tool_start":
                tool_name = event.get("name", "Tool")
                tool_input = event.get("data", {}).get("input")
                current_step = cl.Step(name=f"Executing: {tool_name}", type="tool")
                current_step.input = tool_input
                await current_step.send()

            # Close the step when tool finishes
            elif kind == "on_tool_end":
                if current_step:
                    current_step.output = str(event.get("data", {}).get("output", ""))
                    await current_step.update()
                    current_step = None

            # Stream final tokens to the user
            elif kind == "on_chat_model_stream":
                content = event["data"]["chunk"].content
                node = event.get("metadata", {}).get("langgraph_node")

                if content and node in ("synthesize", "general_responder"):
                    await final_response.stream_token(content)

        # Send any non-streamed final message if tokens weren't streamed
        if not final_response.content:
            state = await graph.aget_state(config)
            if state and state.values.get("messages"):
                last_msg = state.values["messages"][-1]
                if getattr(last_msg, "content", None):
                    final_response.content = last_msg.content

        await final_response.send()

    except Exception as e:
        await cl.Message(content=f"Error: {str(e)}").send()