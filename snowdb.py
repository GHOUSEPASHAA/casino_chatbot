
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect
from snowflake.sqlalchemy import URL

from langchain_community.utilities import SQLDatabase

load_dotenv()


# --------------------------------------------------
# 1. Snowflake connection
# --------------------------------------------------

connection_url = URL(
    account=os.environ["SNOWFLAKE_ACCOUNT"],
    user=os.environ["SNOWFLAKE_USER"],
    password=os.environ["SNOWFLAKE_PASSWORD"],
    warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
    database=os.environ["SNOWFLAKE_DATABASE"],
    schema=os.getenv("SNOWFLAKE_SCHEMA", "GOLD"),
    role=os.getenv("SNOWFLAKE_ROLE"),
)

engine = create_engine(
    connection_url,
    pool_pre_ping=True
)


# --------------------------------------------------
# 2. Snowflake materialized view compatibility
# --------------------------------------------------

# This Snowflake dialect does not implement this
# SQLAlchemy reflection method.
# Return an empty list because we only need tables and views.

engine.dialect.get_materialized_view_names = (
    lambda connection, schema=None, **kwargs: []
)


# --------------------------------------------------
# 3. Retrieve GOLD objects
# --------------------------------------------------

def get_gold_objects():

    inspector = inspect(engine)

    schema = os.getenv("SNOWFLAKE_SCHEMA", "GOLD")

    tables = inspector.get_table_names(schema=schema)

    views = inspector.get_view_names(schema=schema)

    return sorted(set(tables + views))


# --------------------------------------------------
# 4. Initialize SQLDatabase
# --------------------------------------------------

db = SQLDatabase(
    engine=engine,
    schema=os.getenv("SNOWFLAKE_SCHEMA", "GOLD"),
    view_support=True,
    sample_rows_in_table_info=2
)


# --------------------------------------------------
# 5. Verify hotel view reflection
# --------------------------------------------------

inspector = inspect(engine)

hotel_view = "VW_LLM_HOTEL_STAYS"

print("Hotel view columns:")

columns = inspector.get_columns(
    hotel_view,
    schema=os.getenv("SNOWFLAKE_SCHEMA", "GOLD")
)

for column in columns:
    print(column["name"], column["type"])


print("Snowflake connection and view reflection successful!")
