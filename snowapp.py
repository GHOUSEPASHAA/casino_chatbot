
import os
import json
import asyncio
import chainlit as cl
from snowdb import get_medical_test_names
from dotenv import load_dotenv
from chainlit.types import ThreadDict
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
)
from langchain_openai import ChatOpenAI
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from medical_dashboard_service import get_medical_dashboard_data
from auth import authenticate_user
from snowagent import graph
from snowflake_datalayer import SnowflakeDataLayer


load_dotenv()

CONTEXT_HISTORY_MESSAGE_LIMIT = 10


# --------------------------------------------------
# 1. Azure OpenAI - Follow-up Question Generator
# --------------------------------------------------
followup_llm = ChatOpenAI(
    model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    base_url=os.environ["AZURE_OPENAI_BASEURL"],
    temperature=0.3,
)


async def generate_followup_questions(
    user_question: str,
    chatbot_answer: str,
) -> list[str]:
    """
    Generate three contextual follow-up questions
    based on the user's question and chatbot's answer.
    """

    if not chatbot_answer or not chatbot_answer.strip():
        return []

    system_prompt = """
You generate follow-up questions for a medical test results chatbot.

Generate exactly 3 short, relevant follow-up questions.

Rules:
1. Questions must relate to the user's question and chatbot's answer.
2. Do not invent test results, values, diagnoses, or medical conditions.
3. Do not assume that additional medical records are available.
4. Do not repeat the original user question.
5. Prefer questions about:
   - Understanding medical test results
   - High or low test values
   - Reference ranges
   - Comparing available historical results
   - Clarifying the chatbot's answer
6. Do not provide diagnoses or treatment recommendations.
7. Return only a valid JSON array containing 3 strings.
8. Do not include Markdown or explanations.

Example output:
[
  "What does my high glucose result mean?",
  "How does my glucose compare with its reference range?",
  "Are previous glucose results available for comparison?"
]
"""

    user_prompt = (
        f"Original user question:\n{user_question}\n\n"
        f"Chatbot answer:\n{chatbot_answer[:6000]}"
    )

    try:
        response = await followup_llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])

        content = response.content

        if not isinstance(content, str):
            return []

        content = content.strip()

        # Handle occasional Markdown JSON fences
        if content.startswith("```"):
            lines = content.splitlines()
            if len(lines) >= 3:
                content = "\n".join(lines[1:-1]).strip()

        questions = json.loads(content)

        if not isinstance(questions, list):
            return []

        cleaned_questions = []
        seen = {user_question.strip().casefold()}

        for question in questions:
            if not isinstance(question, str):
                continue

            question = question.strip()

            if not question:
                continue

            if not question.endswith("?"):
                question += "?"

            normalized = question.casefold()

            if normalized in seen:
                continue

            seen.add(normalized)
            cleaned_questions.append(question)

            if len(cleaned_questions) == 3:
                break

        return cleaned_questions

    except Exception as error:
        print(
            "Follow-up question generation failed:",
            str(error),
        )
        return []


# --------------------------------------------------
# 2. Display Dynamic Follow-up Questions
# --------------------------------------------------
async def show_followup_questions(
    user_question: str,
    chatbot_answer: str,
):
    questions = await generate_followup_questions(
        user_question=user_question,
        chatbot_answer=chatbot_answer,
    )

    if not questions:
        return

    actions = [
        cl.Action(
            name="medical_followup",
            payload={"question": question},
            label=question,
        )
        for question in questions
    ]

    await cl.Message(
        content="### Suggested Follow-up Questions",
        actions=actions,
    ).send()


# --------------------------------------------------
# 3. Medical Dashboard
# --------------------------------------------------
async def show_medical_dashboard():
    user = cl.user_session.get("user")

    print("========== DASHBOARD DEBUG ==========")
    print(
        "Authenticated User ID:",
        user.identifier if user else None,
    )
    print("=====================================")

    if not user or not user.identifier:
        await cl.Message(
            content="Please sign in to view your medical dashboard."
        ).send()
        return

    try:
        dashboard_data = get_medical_dashboard_data(
            user_id=user.identifier
        )

        dashboard = cl.CustomElement(
            name="MedicalDashboard",
            props=dashboard_data,
            display="inline",
        )

        await cl.Message(
            content="### My Medical Results Dashboard",
            elements=[dashboard],
        ).send()

    except Exception:
        await cl.Message(
            content=(
                "Unable to load your medical dashboard. "
                "Please try again later."
            )
        ).send()
        raise


# --------------------------------------------------
# 4. Register Data Layer
# --------------------------------------------------
@cl.data_layer
def get_data_layer():
    return SnowflakeDataLayer()


# --------------------------------------------------
# 5. Authentication Callback
# --------------------------------------------------
@cl.password_auth_callback
async def password_auth_callback(
    username: str,
    password: str,
):
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
# 6. New Chat Session
# --------------------------------------------------
@cl.on_chat_start
async def on_chat_start():
    user = cl.user_session.get("user")

    if user and user.identifier:
        test_names = await asyncio.to_thread(
            get_medical_test_names,
            user.identifier
        )
    else:
        test_names = []

    cl.user_session.set("medical_test_names", test_names)
    print("AUTOCOMPLETE TEST COUNT:", len(test_names))

    thread_id = (
        cl.context.session.thread_id
        or cl.context.session.id
    )

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

    await show_medical_dashboard()


# --------------------------------------------------
# 7. Resume Historical Chat
# --------------------------------------------------
@cl.on_chat_resume
async def on_chat_resume(thread: ThreadDict):
    thread_id = thread["id"]

    cl.user_session.set("thread_id", thread_id)

    user = cl.user_session.get("user")

    if not user:
        raise RuntimeError(
            "Cannot restore chat history without an authenticated user."
        )

    history = await SnowflakeDataLayer().get_chat_history(
        thread_id=thread_id,
        user_id=user.identifier,
        limit=CONTEXT_HISTORY_MESSAGE_LIMIT,
    )

    messages = [
        HumanMessage(content=item["content"])
        if item["role"] == "user"
        else AIMessage(content=item["content"])
        for item in history
    ]

    await graph.aupdate_state(
        {"configurable": {"thread_id": thread_id}},
        {
            "messages": [
                RemoveMessage(id=REMOVE_ALL_MESSAGES),
                *messages,
            ]
        },
    )


# --------------------------------------------------
# 8. Dynamic Follow-up Button Callback
# --------------------------------------------------
@cl.action_callback("medical_followup")
async def handle_medical_followup(action: cl.Action):
    question = action.payload.get("question")

    if (
        not isinstance(question, str)
        or not question.strip()
        or len(question) > 500
    ):
        await cl.Message(
            content="Invalid follow-up question."
        ).send()
        return

    question = question.strip()

    await action.remove()

    await cl.Message(
        content=question,
        type="user",
    ).send()

    await on_message(
        cl.Message(content=question)
    )


# --------------------------------------------------
# 9. Message Execution
# --------------------------------------------------
@cl.on_message
async def on_message(message: cl.Message):
    thread_id = cl.user_session.get(
        "thread_id",
        cl.context.session.id,
    )

    user = cl.user_session.get("user")
    user_id = user.identifier if user else None

    config = {
        "configurable": {
            "thread_id": thread_id,
            "user_id": user_id,
        }
    }

    state_input = {
        "messages": [
            HumanMessage(content=message.content)
        ]
    }

    final_response = cl.Message(content="")
    current_step = None

    try:
        async for event in graph.astream_events(
            state_input,
            config=config,
            version="v2",
        ):
            kind = event["event"]

            if kind == "on_tool_start":
                tool_name = event.get("name", "Tool")
                tool_input = event.get("data", {}).get("input")

                current_step = cl.Step(
                    name=f"Executing: {tool_name}",
                    type="tool",
                )

                current_step.input = tool_input
                await current_step.send()

            elif kind == "on_tool_end":
                if current_step:
                    current_step.output = str(
                        event.get("data", {}).get(
                            "output", ""
                        )
                    )

                    await current_step.update()
                    current_step = None

            elif kind == "on_chat_model_stream":
                content = event["data"]["chunk"].content

                node = event.get(
                    "metadata", {}
                ).get("langgraph_node")

                if content and node in (
                    "synthesize",
                    "general_responder",
                ):
                    await final_response.stream_token(content)

        # Fallback if streaming produced no content
        if not final_response.content:
            state = await graph.aget_state(config)

            if state and state.values.get("messages"):
                last_msg = state.values["messages"][-1]

                if getattr(last_msg, "content", None):
                    final_response.content = last_msg.content

        # Send the chatbot's final answer
        await final_response.send()

    except Exception as e:
        await cl.Message(
            content=f"Error: {str(e)}"
        ).send()
        return

    # Generate follow-up suggestions after successful response
    await show_followup_questions(
        user_question=message.content,
        chatbot_answer=str(final_response.content or ""),
    )
