
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect
from snowflake.sqlalchemy import URL

from langchain_community.utilities import SQLDatabase

load_dotenv()

# --------------------------------------------------
# 1. Snowflake configuration
# --------------------------------------------------

DATABASE = os.environ["SNOWFLAKE_DATABASE"]
SCHEMA = os.getenv("SNOWFLAKE_SCHEMA", "BRONZE")
TABLE = "consolidated_test_results"

connection_url = URL(
    account=os.environ["SNOWFLAKE_ACCOUNT"],
    user=os.environ["SNOWFLAKE_USER"],
    password=os.environ["SNOWFLAKE_PASSWORD"],
    warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
    database=DATABASE,
    schema=SCHEMA,
    role=os.getenv("SNOWFLAKE_ROLE"),
)

engine = create_engine(
    connection_url,
    pool_pre_ping=True
)

# --------------------------------------------------
# 2. Materialized view compatibility
# --------------------------------------------------

engine.dialect.get_materialized_view_names = (
    lambda connection, schema=None, **kwargs: []
)


# --------------------------------------------------
# 3. Verify connection
# --------------------------------------------------

def verify_connection():

    with engine.connect() as conn:

        result = conn.exec_driver_sql("""
            SELECT
                CURRENT_ACCOUNT(),
                CURRENT_USER(),
                CURRENT_DATABASE(),
                CURRENT_SCHEMA(),
                CURRENT_ROLE(),
                CURRENT_WAREHOUSE()
        """)

        print("\n--- SNOWFLAKE CONNECTION ---")
        print(result.fetchone())


# --------------------------------------------------
# 4. Verify consolidated table
# --------------------------------------------------

def verify_table():

    inspector = inspect(engine)

    tables = inspector.get_table_names(schema=SCHEMA)
    views = inspector.get_view_names(schema=SCHEMA)

    print("\n--- AVAILABLE TABLES ---")
    print(tables)

    print("\n--- AVAILABLE VIEWS ---")
    print(views)

    all_objects = tables + views

    if TABLE not in all_objects:

        raise RuntimeError(
            f"{TABLE} not found in {DATABASE}.{SCHEMA}.\n"
            f"Available objects: {all_objects}"
        )

    columns = inspector.get_columns(
        TABLE,
        schema=SCHEMA
    )

    print(f"\n--- {TABLE} COLUMNS ---")

    for column in columns:
        print(f"{column['name']} : {column['type']}")

    return columns


# --------------------------------------------------
# 5. Initialize SQLDatabase
# --------------------------------------------------

def initialize_database():

    print("\nInitializing SQLDatabase...")

    database = SQLDatabase(
        engine=engine,
        schema=SCHEMA,
        include_tables=[TABLE],
        view_support=True,
        sample_rows_in_table_info=3
    )

    print("\nAvailable SQLDatabase objects:")
    print(database.get_usable_table_names())

    print("\n--- TABLE INFORMATION ---")
    print(database.get_table_info([TABLE]))

    return database


# --------------------------------------------------
# 6. Execution
# --------------------------------------------------

verify_connection()

verify_table()

db = initialize_database()

print("\nSnowflake connection and table verification successful!")
snowflake_engine = db._engine
print(type(snowflake_engine))



# --------------------------------------------------
# 7. Dynamic Medical Test Names for Autocomplete
# --------------------------------------------------

from sqlalchemy import text



def get_medical_test_names(user_id: str) -> list[str]:
    if not user_id:
        return []

    query = text("""
        SELECT DISTINCT TRIM(TEST_NAME) AS TEST_NAME
        FROM MEDICAL.BRONZE.CONSOLIDATED_TEST_RESULTS
        WHERE USER_ID = :user_id
          AND TEST_NAME IS NOT NULL
          AND TRIM(TEST_NAME) <> ''
        ORDER BY TEST_NAME
    """)

    with engine.connect() as conn:
        try:
            conn.execute(
                text("SET CURRENT_APP_USER = :user_id"),
                {"user_id": str(user_id)}
            )

            rows = conn.execute(
                query,
                {"user_id": str(user_id)}
            ).scalars().all()

            return list(rows)

        finally:
            try:
                conn.execute(
                    text("UNSET CURRENT_APP_USER")
                )
            except Exception:
                conn.invalidate()
                raise

