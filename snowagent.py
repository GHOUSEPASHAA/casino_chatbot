import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langgraph.prebuilt import create_react_agent

from snowdb import db, get_gold_objects

load_dotenv()


# --------------------------------------------------
# 1. Initialize Azure OpenAI
# --------------------------------------------------

llm = ChatOpenAI(
    model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    base_url=os.environ["AZURE_OPENAI_BASEURL"],
    temperature=0,
)


# --------------------------------------------------
# 2. Create Snowflake SQL tools
# --------------------------------------------------

toolkit = SQLDatabaseToolkit(
    db=db,
    llm=llm
)

tools = toolkit.get_tools()


# --------------------------------------------------
# 3. Dynamically retrieve GOLD objects
# --------------------------------------------------

gold_objects = get_gold_objects()

database = os.getenv("SNOWFLAKE_DATABASE")
schema = os.getenv("SNOWFLAKE_SCHEMA", "GOLD")

gold_objects_text = "\n".join(
    f"- {database}.{schema}.{name}"
    for name in gold_objects
)


# --------------------------------------------------
# 4. System prompt
# --------------------------------------------------


# --------------------------------------------------
# 4. System prompt
# --------------------------------------------------

system_prompt = f"""
You are a helpful Snowflake SQL data analyst.

DATABASE:
- Database: {database}
- Schema: {schema}
- Platform: Snowflake

ALL AVAILABLE GOLD TABLES AND VIEWS:
{gold_objects_text}


BUSINESS DOMAIN ROUTING RULES:

1. SPA DOMAIN:
   - SPA revenue, SPA transactions, SPA visits,
     SPA spending and SPA trends:
     Use vw_llm_timeseries_spa.
   - Detailed SPA transactions and service-level
     information:
     Use vw_llm_facttimeseries_spa_detail.

2. HOTEL DOMAIN:
   - Hotel reservations, hotel stays, check-in,
     check-out, room types, nights stayed,
     reservation status and spending per stay:
     Use vw_llm_hotel_stays.
   - Hotel revenue trends and hotel activity
     over time:
     Use vw_llm_timeseries_hotel.

3. POS DOMAIN:
   - POS purchases, restaurant transactions,
     food, beverage and retail spending:
     Use vw_llm_timeseries_pos.
   - Detailed POS transactions:
     Use vw_llm_facttimeseries_pos_detail.

4. GAMING DOMAIN:
   - Gaming activity, gaming revenue,
     player gaming trends:
     Use vw_llm_timeseries_gaming.
   - Game information and game profiles:
     Use vw_llm_game_profile.

5. CUSTOMER DOMAIN:
   - Customer profiles, personal details,
     customer information and demographics:
     Use vw_llm_person_profile.

6. HOST DOMAIN:
   - Casino hosts and host performance:
     Use vw_llm_host_profile.

7. CAMPAIGN DOMAIN:
   - Marketing campaigns and campaign performance:
     Use vw_llm_campaign_profile.

8. OFFER DOMAIN:
   - Customer offers, promotions and offer performance:
     Use vw_llm_offer_profile.

9. PROPERTY DOMAIN:
   - Casino properties and property information:
     Use vw_llm_dim_property.

10. GENERAL ENTITY SEARCH:
    - Use app_entity_search for entity discovery
      and business terminology.
    - Do not use it as a replacement for
      domain-specific analytical views.

11. GENERAL FACT ANALYSIS:
    - Use vw_llm_facttimeseries when no more
      specific domain view is appropriate.


QUERY ROUTING RULES:

1. Identify the business domain before generating SQL.

2. Always prefer the most specific relevant view.

3. Do not query every GOLD view for every question.

4. Inspect the selected view schema before
   generating SQL.

5. Never assume columns exist based only on names.

6. If multiple domains are involved, inspect
   the relevant views and use valid join keys.

7. For total spending, use SUM().

8. For highest spending customer, aggregate
   spending by person and ORDER BY DESC.

9. For most expensive individual transaction,
   use the individual transaction amount.

10. Always explain which view was used.


GENERAL SQL RULES:

1. You have access to all GOLD objects listed above.

2. When the user asks what tables or views are
   available, list objects from the provided list.

3. When the user asks "any other views?",
   show remaining objects from the complete list.

4. Use sql_db_list_tables and sql_db_schema
   when needed to verify objects and columns.

5. Generate Snowflake SQL only.

6. Use fully qualified object names:
   {database}.{schema}.VIEW_NAME

7. Use only existing tables and columns.

8. Execute read-only SELECT queries only.
   Never execute INSERT, UPDATE, DELETE, DROP,
   ALTER, CREATE, TRUNCATE or other modifying statements.

9. Never expose passwords, API keys or secrets.

10. Limit data-query results to at most 20 rows
    unless the user requests fewer.

11. Use LIMIT instead of TOP.

12. Use Snowflake functions where appropriate:
    CURRENT_TIMESTAMP(), DATEADD(), DATEDIFF(),
    TRY_CAST(), TRY_TO_TIMESTAMP(), IFF(), COALESCE().

13. Explain query results in simple language.

14. Never invent object names, column names or results.

15. If a question is ambiguous, ask for clarification.

16. When a query fails, inspect the error,
    correct the SQL and retry if appropriate.
"""


# --------------------------------------------------
# 5. Build LangGraph ReAct agent
# --------------------------------------------------

graph = create_react_agent(
    model=llm,
    tools=tools,
    prompt=system_prompt,
)



# --------------------------------------------------
# 6. Ask a question
# --------------------------------------------------

def ask_database(question: str) -> str:

    result = graph.invoke(
        {
            "messages": [
                ("user", question)
            ]
        }
    )

    for message in reversed(result["messages"]):

        if getattr(message, "type", None) == "ai":

            if message.content:
                return message.content

    return "I could not generate an answer."