
import chainlit as cl
from snowagent import graph



@cl.on_chat_start
async def on_chat_start():

    cl.user_session.set("messages", [])

    welcome = """
# Welcome to  Casino AI Assistant! 🎰

I'm your AI-powered data assistant. Ask questions about
casino operations, customer spending, revenue and performance.

## What can you explore?

### 🏨 Hotels
- Show hotel reservations and check-in details.
- Which property generated the highest hotel revenue?

### 🧖 SPA
- Which person spent the most on SPA?
- Which SPA service generated the highest revenue?
 

### 🎮 Gaming
- Which customer generated the highest gaming revenue?


### 👤 Customers & Hosts
- Who are the top casino hosts?


### 🍽️ POS
- Which person spent the most on POS?
- Which property generated the highest POS revenue?

### 🎁 Offers & Campaigns
- Which campaign performed best?
 

---

**Start by asking any question about  Casino data!**
"""

    await cl.Message(content=welcome).send()


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
