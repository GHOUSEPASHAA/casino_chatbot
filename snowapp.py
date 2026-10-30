
import chainlit as cl
from snowagent import graph


@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("messages", [])

    await cl.Message(
        content="Welcome! I'm your Snowflake AI Data Assistant. Ask me anything about your GOLD tables and views."
    ).send()


@cl.on_message
async def on_message(message: cl.Message):

    # Retrieve conversation history
    messages = cl.user_session.get("messages", [])

    # Add user question
    messages.append(("user", message.content))

    try:
        # Execute LangGraph agent
        result = await cl.make_async(graph.invoke)(
            {"messages": messages}
        )

        # Save conversation history
        cl.user_session.set(
            "messages",
            result["messages"]
        )

        # Get final AI response
        answer = ""

        for msg in reversed(result["messages"]):
            if getattr(msg, "type", None) == "ai" and msg.content:
                answer = msg.content
                break

        await cl.Message(
            content=answer or "I couldn't generate an answer."
        ).send()

    except Exception as e:

        await cl.Message(
            content=f"Error: {str(e)}"
        ).send()
