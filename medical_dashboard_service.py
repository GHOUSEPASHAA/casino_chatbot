
from sqlalchemy import text
from snowdb import engine


def get_medical_dashboard_data(user_id: str):
    """
    Fetch dashboard statistics for the authenticated user.
    Snowflake row access policy enforces user isolation.
    """

    if not user_id:
        raise ValueError(
            "Authenticated user ID is required."
        )

    query = text("""
        SELECT
            COUNT(*) AS TOTAL_TESTS,

            COUNT_IF(
                UPPER(TRIM(RESULT_FLAG)) = 'NOT_FLAGGED'
            ) AS NORMAL_TESTS,

            COUNT_IF(
                UPPER(TRIM(RESULT_FLAG)) IN ('HIGH', 'LOW')
            ) AS ABNORMAL_TESTS,

            COUNT(DISTINCT REPORT_ID) AS TOTAL_REPORTS

        FROM MEDICAL.BRONZE.CONSOLIDATED_TEST_RESULTS
        WHERE USER_ID = :user_id
    """)

    with engine.connect() as conn:

        # Set the authenticated user in this Snowflake session.
        conn.execute(
            text("SET CURRENT_APP_USER = :user_id"),
            {"user_id": str(user_id)}
        )

        # Execute on the SAME connection.
        row = conn.execute(
            query,
            {"user_id": str(user_id)}
        ).mappings().one()

        # Clear the session variable before returning
        # the connection to SQLAlchemy's connection pool.
        try:
            conn.execute(text("UNSET CURRENT_APP_USER"))
        except Exception:
            conn.invalidate()
            raise

        data = {
            str(key).upper(): value
            for key, value in row.items()
        }

    return {
        "total_tests": int(data.get("TOTAL_TESTS") or 0),
        "normal_tests": int(data.get("NORMAL_TESTS") or 0),
        "abnormal_tests": int(data.get("ABNORMAL_TESTS") or 0),
        "total_reports": int(data.get("TOTAL_REPORTS") or 0),
    }
