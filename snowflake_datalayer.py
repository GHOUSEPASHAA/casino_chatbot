
import json
from datetime import datetime
from typing import Optional, Dict, List, Any

from chainlit.data import BaseDataLayer
from chainlit.types import (
    ThreadDict,
    ThreadFilter,
    Pagination,
    PaginatedResponse,
    PageInfo,
    Feedback,
)
from chainlit.user import PersistedUser
from chainlit.step import StepDict
from chainlit.element import ElementDict

from sqlalchemy import text
from snowdb import engine


# --------------------------------------------------
# 1. Safe Type Helpers
# --------------------------------------------------

def _normalize_row(mapping_row: Any) -> Dict[str, Any]:
    if not mapping_row:
        return {}

    return {
        str(k).upper(): v
        for k, v in mapping_row.items()
    }


def _format_dt(dt_val: Any) -> Optional[str]:
    """Safely format datetime or string timestamps."""

    if not dt_val:
        return None

    if hasattr(dt_val, "isoformat"):
        return dt_val.isoformat()

    return str(dt_val)


def _safe_dict(val: Any) -> Dict[str, Any]:
    """Ensure Snowflake VARIANT metadata returns as a dict."""

    if not val:
        return {}

    if isinstance(val, dict):
        return val

    if isinstance(val, str):
        try:
            parsed = json.loads(val)

            return (
                parsed
                if isinstance(parsed, dict)
                else {}
            )

        except (ValueError, TypeError):
            return {}

    return {}


def _safe_list(val: Any) -> List[str]:
    """Ensure Snowflake VARIANT tags return as a list."""

    if not val:
        return []

    if isinstance(val, list):
        return [str(x) for x in val]

    if isinstance(val, str):
        try:
            parsed = json.loads(val)

            if isinstance(parsed, list):
                return [
                    str(x)
                    for x in parsed
                ]

        except (ValueError, TypeError):
            pass

    return []


# --------------------------------------------------
# 2. Safe JSON Serialization
# --------------------------------------------------

def _safe_json_str(val: Any) -> str:
    """
    Serialize values for Snowflake PARSE_JSON.

    Plain text is stored as a JSON string.

    Example:
        Hello World

    Stored JSON:
        "Hello World"

    This prevents creation of new
    {"value": "..."} wrappers.
    """

    if val is None:
        return "null"

    if isinstance(val, str):
        return json.dumps(
            val,
            ensure_ascii=False,
        )

    return json.dumps(
        val,
        ensure_ascii=False,
        default=str,
    )


# --------------------------------------------------
# 3. Restore Message Text
# --------------------------------------------------

def _restore_message_text(val: Any) -> str:
    """
    Restore plain text from Snowflake VARIANT.

    Supports:
    - Plain text
    - JSON-encoded strings
    - Escaped newline characters
    - Legacy {"value": "..."} records
    - Structured dictionaries and lists

    Examples:

    Input:
        '"Hello World"'

    Output:
        Hello World

    Input:
        '"\\n# Welcome\\n"'

    Output:
        Actual multiline Markdown

    Input:
        {"value": "Hello World"}

    Output:
        Hello World
    """

    if val is None:
        return ""

    # ----------------------------------------------
    # Dictionary values
    # ----------------------------------------------

    if isinstance(val, dict):

        if set(val.keys()) == {"value"}:

            return _restore_message_text(
                val["value"]
            )

        return json.dumps(
            val,
            ensure_ascii=False,
            default=str,
        )

    # ----------------------------------------------
    # List values
    # ----------------------------------------------

    if isinstance(val, list):

        return json.dumps(
            val,
            ensure_ascii=False,
            default=str,
        )

    # ----------------------------------------------
    # String values
    # ----------------------------------------------

    if isinstance(val, str):

        try:
            parsed = json.loads(val)

            # JSON string literal:
            # '"Hello\\nWorld"'
            #
            # Becomes actual multiline text.
            if isinstance(parsed, str):
                return parsed

            # Legacy JSON object:
            # {"value": "Hello"}
            if (
                isinstance(parsed, dict)
                and set(parsed.keys()) == {"value"}
            ):

                return _restore_message_text(
                    parsed["value"]
                )

        except (json.JSONDecodeError, TypeError):
            pass

        return val

    return str(val)


# --------------------------------------------------
# 4. Snowflake Data Layer
# --------------------------------------------------

class SnowflakeDataLayer(BaseDataLayer):

    # --------------------------------------------------
    # User Operations
    # --------------------------------------------------

    
    async def get_user(
        self,
        identifier: str,
    ) -> Optional[PersistedUser]:

        with engine.connect() as conn:

            raw_row = conn.execute(
                text("""
                    SELECT
                        USER_ID,
                        TENANT_ID,
                        EMAIL,
                        FULL_NAME,
                        ROLE
                    FROM MEDICAL.BRONZE.USERS
                    WHERE USER_ID = :user_id
                       OR LOWER(EMAIL) = LOWER(:user_id)
                    LIMIT 1
                """),
                {
                    "user_id": identifier
                },
            ).mappings().first()

            if not raw_row:
                return None

            row = _normalize_row(raw_row)

            return PersistedUser(
                id=str(row.get("USER_ID", "")),
                identifier=str(row.get("USER_ID", "")),
                createdAt=datetime.utcnow().isoformat(),
                metadata={
                    "email": row.get("EMAIL", ""),
                    "name": row.get("FULL_NAME", ""),
                    "role": row.get("ROLE", ""),
                    "tenant_id": row.get("TENANT_ID"),
                },
            )
    

    async def create_user(
        self,
        user: Any,
    ) -> Optional[PersistedUser]:

        ident = (
            getattr(user, "identifier", None)
            or (
                user.get("identifier")
                if isinstance(user, dict)
                else str(user)
            )
        )

        return await self.get_user(ident)

    # --------------------------------------------------
    # Thread Author & Diagnostics
    # --------------------------------------------------

    async def get_thread_author(
        self,
        thread_id: str,
    ) -> str:

        with engine.connect() as conn:

            raw_row = conn.execute(
                text("""
                    SELECT USER_ID
                    FROM MEDICAL.BRONZE.CHAINLIT_THREADS
                    WHERE ID = :thread_id
                    LIMIT 1
                """),
                {
                    "thread_id": thread_id
                },
            ).mappings().first()

            if not raw_row:
                return ""

            row = _normalize_row(raw_row)

            return str(
                row.get("USER_ID", "")
            )

    async def build_debug_url(self) -> str:
        return ""

    async def close(self) -> None:
        pass

    # --------------------------------------------------
    # Thread Operations
    # --------------------------------------------------

    async def get_thread(
        self,
        thread_id: str,
    ) -> Optional[ThreadDict]:

        with engine.connect() as conn:

            raw_thread = conn.execute(
                text("""
                    SELECT
                        ID,
                        USER_ID,
                        NAME,
                        CREATED_AT,
                        METADATA,
                        TAGS
                    FROM MEDICAL.BRONZE.CHAINLIT_THREADS
                    WHERE ID = :thread_id
                """),
                {
                    "thread_id": thread_id
                },
            ).mappings().first()

            if not raw_thread:
                return None

            thread_row = _normalize_row(
                raw_thread
            )

            steps_rows = conn.execute(
                text("""
                    SELECT
                        ID,
                        THREAD_ID,
                        NAME,
                        TYPE,
                        IS_ERROR,
                        INPUT,
                        OUTPUT,
                        CREATED_AT,
                        START_TIME,
                        END_TIME,
                        METADATA,
                        PARENT_ID
                    FROM MEDICAL.BRONZE.CHAINLIT_STEPS
                    WHERE THREAD_ID = :thread_id
                    ORDER BY CREATED_AT ASC
                """),
                {
                    "thread_id": thread_id
                },
            ).mappings().all()

            steps: List[StepDict] = []

            for raw_s in steps_rows:

                s = _normalize_row(raw_s)

                # Restore actual message text.
                # Handles both old and new records.
                output_str = _restore_message_text(
                    s.get("OUTPUT")
                )

                input_str = _restore_message_text(
                    s.get("INPUT")
                )

                steps.append({
                    "id": str(
                        s.get("ID", "")
                    ),
                    "threadId": str(
                        s.get("THREAD_ID", "")
                    ),
                    "name": str(
                        s.get("NAME") or "Step"
                    ),
                    "type": str(
                        s.get("TYPE") or "run"
                    ),
                    "isError": bool(
                        s.get("IS_ERROR", False)
                    ),
                    "input": input_str,
                    "output": output_str,
                    "createdAt": _format_dt(
                        s.get("CREATED_AT")
                    ),
                    "start": _format_dt(
                        s.get("START_TIME")
                    ),
                    "end": _format_dt(
                        s.get("END_TIME")
                    ),
                    "metadata": _safe_dict(
                        s.get("METADATA")
                    ),
                    "parentId": (
                        str(s["PARENT_ID"])
                        if s.get("PARENT_ID")
                        else None
                    ),
                })

            user_id_str = str(
                thread_row.get("USER_ID", "")
            )

            return {
                "id": str(
                    thread_row.get("ID", "")
                ),
                "createdAt": (
                    _format_dt(
                        thread_row.get("CREATED_AT")
                    )
                    or datetime.utcnow().isoformat()
                ),
                "name": str(
                    thread_row.get("NAME")
                    or "New Chat"
                ),
                "userId": user_id_str,
                "userIdentifier": user_id_str,
                "tags": _safe_list(
                    thread_row.get("TAGS")
                ),
                "metadata": _safe_dict(
                    thread_row.get("METADATA")
                ),
                "steps": steps,
                "elements": [],
            }

    async def get_chat_history(
        self,
        thread_id: str,
        user_id: str,
        limit: int = 10,
    ) -> List[Dict[str, str]]:
        if limit < 1:
            raise ValueError("limit must be at least 1")

        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT
                        s.TYPE,
                        s.OUTPUT
                    FROM MEDICAL.BRONZE.CHAINLIT_STEPS s
                    INNER JOIN MEDICAL.BRONZE.CHAINLIT_THREADS t
                        ON t.ID = s.THREAD_ID
                    WHERE s.THREAD_ID = :thread_id
                        AND t.USER_ID = :user_id
                        AND s.TYPE IN (
                            'user_message',
                            'assistant_message'
                        )
                        AND COALESCE(s.IS_ERROR, FALSE) = FALSE
                    ORDER BY s.CREATED_AT DESC, s.ID DESC
                    LIMIT :limit
                """),
                {
                    "thread_id": thread_id,
                    "user_id": user_id,
                    "limit": limit,
                },
            ).mappings().all()

        history: List[Dict[str, str]] = []
        for raw_row in reversed(rows):
            row = _normalize_row(raw_row)
            content = _restore_message_text(row.get("OUTPUT"))
            if not content:
                continue

            history.append({
                "role": (
                    "user"
                    if row.get("TYPE") == "user_message"
                    else "assistant"
                ),
                "content": content,
            })

        return history

    # --------------------------------------------------
    # List Threads
    # --------------------------------------------------

    async def list_threads(
        self,
        pagination: Pagination,
        filter: ThreadFilter,
    ) -> PaginatedResponse[ThreadDict]:

        with engine.connect() as conn:

            query = """
                SELECT
                    ID,
                    USER_ID,
                    NAME,
                    CREATED_AT,
                    METADATA,
                    TAGS
                FROM MEDICAL.BRONZE.CHAINLIT_THREADS
                WHERE USER_ID = :user_id
            """

            params: Dict[str, Any] = {
                "user_id": filter.userId
            }

            if filter.search:

                query += (
                    " AND LOWER(NAME) LIKE :search"
                )

                params["search"] = (
                    f"%{filter.search.lower()}%"
                )

            query += " ORDER BY CREATED_AT DESC"

            if pagination.first:
                query += (
                    f" LIMIT {int(pagination.first)}"
                )

            rows = conn.execute(
                text(query),
                params,
            ).mappings().all()

            data: List[ThreadDict] = []

            for raw_r in rows:

                r = _normalize_row(raw_r)

                uid = str(
                    r.get("USER_ID", "")
                )

                data.append({
                    "id": str(
                        r.get("ID", "")
                    ),
                    "createdAt": _format_dt(
                        r.get("CREATED_AT")
                    ),
                    "name": str(
                        r.get("NAME") or "New Chat"
                    ),
                    "userId": uid,
                    "userIdentifier": uid,
                    "tags": _safe_list(
                        r.get("TAGS")
                    ),
                    "metadata": _safe_dict(
                        r.get("METADATA")
                    ),
                    "steps": [],
                    "elements": [],
                })

            return PaginatedResponse(
                data=data,
                pageInfo=PageInfo(
                    hasNextPage=False,
                    startCursor=None,
                    endCursor=None,
                ),
            )

    # --------------------------------------------------
    # Update Thread
    # --------------------------------------------------

    async def update_thread(
        self,
        thread_id: str,
        name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
    ):

        with engine.begin() as conn:

            conn.execute(
                text("""
                    MERGE INTO MEDICAL.BRONZE.CHAINLIT_THREADS t

                    USING (
                        SELECT
                            :id AS ID,
                            :user_id AS USER_ID,
                            :name AS NAME,
                            PARSE_JSON(:metadata) AS METADATA,
                            PARSE_JSON(:tags) AS TAGS
                    ) s

                    ON t.ID = s.ID

                    WHEN MATCHED THEN
                        UPDATE SET
                            NAME = COALESCE(
                                s.NAME,
                                t.NAME
                            ),
                            USER_ID = COALESCE(
                                s.USER_ID,
                                t.USER_ID
                            ),
                            METADATA = s.METADATA,
                            TAGS = s.TAGS

                    WHEN NOT MATCHED THEN
                        INSERT (
                            ID,
                            USER_ID,
                            NAME,
                            CREATED_AT,
                            METADATA,
                            TAGS
                        )
                        VALUES (
                            s.ID,
                            s.USER_ID,
                            COALESCE(
                                s.NAME,
                                'New Chat'
                            ),
                            CURRENT_TIMESTAMP(),
                            s.METADATA,
                            s.TAGS
                        )
                """),
                {
                    "id": thread_id,
                    "user_id": user_id,
                    "name": name,
                    "metadata": _safe_json_str(
                        metadata
                    ),
                    "tags": json.dumps(
                        tags or []
                    ),
                },
            )

    # --------------------------------------------------
    # Delete Thread
    # --------------------------------------------------

    async def delete_thread(
        self,
        thread_id: str,
    ):

        with engine.begin() as conn:

            conn.execute(
                text("""
                    DELETE FROM MEDICAL.BRONZE.CHAINLIT_STEPS
                    WHERE THREAD_ID = :thread_id
                """),
                {
                    "thread_id": thread_id
                },
            )

            conn.execute(
                text("""
                    DELETE FROM MEDICAL.BRONZE.CHAINLIT_THREADS
                    WHERE ID = :thread_id
                """),
                {
                    "thread_id": thread_id
                },
            )

    # --------------------------------------------------
    # Step Operations
    # --------------------------------------------------

    async def create_step(
        self,
        step_dict: StepDict,
    ):

        start_val = step_dict.get("start")
        end_val = step_dict.get("end")

        start_dt = (
            datetime.fromisoformat(
                start_val.replace(
                    "Z",
                    "+00:00"
                )
            )
            if start_val
            else datetime.utcnow()
        )

        end_dt = (
            datetime.fromisoformat(
                end_val.replace(
                    "Z",
                    "+00:00"
                )
            )
            if end_val
            else None
        )

        with engine.begin() as conn:

            conn.execute(
                text("""
                    INSERT INTO MEDICAL.BRONZE.CHAINLIT_STEPS (
                        ID,
                        THREAD_ID,
                        NAME,
                        TYPE,
                        IS_ERROR,
                        INPUT,
                        OUTPUT,
                        CREATED_AT,
                        START_TIME,
                        END_TIME,
                        METADATA,
                        PARENT_ID
                    )

                    SELECT
                        :id,
                        :thread_id,
                        :name,
                        :type,
                        :is_error,
                        PARSE_JSON(:input),
                        PARSE_JSON(:output),
                        CURRENT_TIMESTAMP(),
                        :start_time,
                        :end_time,
                        PARSE_JSON(:metadata),
                        :parent_id
                """),
                {
                    "id": step_dict["id"],
                    "thread_id": step_dict["threadId"],
                    "name": (
                        step_dict.get("name")
                        or "Step"
                    ),
                    "type": (
                        step_dict.get("type")
                        or "run"
                    ),
                    "is_error": bool(
                        step_dict.get(
                            "isError",
                            False
                        )
                    ),
                    "input": _safe_json_str(
                        step_dict.get("input")
                    ),
                    "output": _safe_json_str(
                        step_dict.get("output")
                    ),
                    "start_time": start_dt,
                    "end_time": end_dt,
                    "metadata": _safe_json_str(
                        step_dict.get("metadata")
                    ),
                    "parent_id": step_dict.get(
                        "parentId"
                    ),
                },
            )

    # --------------------------------------------------
    # Update Step
    # --------------------------------------------------

    async def update_step(
        self,
        step_dict: StepDict,
    ):

        end_val = step_dict.get("end")

        end_dt = (
            datetime.fromisoformat(
                end_val.replace(
                    "Z",
                    "+00:00"
                )
            )
            if end_val
            else datetime.utcnow()
        )

        with engine.begin() as conn:

            conn.execute(
                text("""
                    UPDATE MEDICAL.BRONZE.CHAINLIT_STEPS

                    SET
                        OUTPUT = PARSE_JSON(:output),
                        IS_ERROR = :is_error,
                        END_TIME = :end_time

                    WHERE ID = :id
                """),
                {
                    "id": step_dict["id"],
                    "output": _safe_json_str(
                        step_dict.get("output")
                    ),
                    "is_error": bool(
                        step_dict.get(
                            "isError",
                            False
                        )
                    ),
                    "end_time": end_dt,
                },
            )

    # --------------------------------------------------
    # Delete Step
    # --------------------------------------------------

    async def delete_step(
        self,
        step_id: str,
    ):

        with engine.begin() as conn:

            conn.execute(
                text("""
                    DELETE FROM MEDICAL.BRONZE.CHAINLIT_STEPS
                    WHERE ID = :step_id
                """),
                {
                    "step_id": step_id
                },
            )

    async def get_favorite_steps(
        self,
        user_id: str,
    ) -> List[Dict[str, Any]]:
        return []

    # --------------------------------------------------
    # Element Operations
    # --------------------------------------------------

    async def get_element(
        self,
        thread_id: str,
        element_id: str,
    ) -> Optional[ElementDict]:
        return None

    async def create_element(
        self,
        element: ElementDict,
    ):
        pass

    async def delete_element(
        self,
        element_id: str,
    ):
        pass

    # --------------------------------------------------
    # Feedback Operations
    # --------------------------------------------------

    async def upsert_feedback(
        self,
        feedback: Feedback,
    ) -> str:

        with engine.begin() as conn:

            conn.execute(
                text("""
                    MERGE INTO MEDICAL.BRONZE.CHAINLIT_FEEDBACKS f

                    USING (
                        SELECT :id AS ID
                    ) s

                    ON f.ID = s.ID

                    WHEN MATCHED THEN
                        UPDATE SET
                            VALUE = :value,
                            COMMENT = :comment

                    WHEN NOT MATCHED THEN
                        INSERT (
                            ID,
                            FOR_ID,
                            THREAD_ID,
                            VALUE,
                            COMMENT
                        )
                        VALUES (
                            :id,
                            :for_id,
                            :thread_id,
                            :value,
                            :comment
                        )
                """),
                {
                    "id": (
                        feedback.id
                        or feedback.forId
                    ),
                    "for_id": feedback.forId,
                    "thread_id": feedback.threadId,
                    "value": feedback.value,
                    "comment": feedback.comment,
                },
            )

        return feedback.id or ""

    async def set_feedback(
        self,
        feedback: Feedback,
    ) -> str:

        return await self.upsert_feedback(
            feedback
        )

    async def delete_feedback(
        self,
        feedback_id: str,
    ) -> bool:

        with engine.begin() as conn:

            conn.execute(
                text("""
                    DELETE FROM MEDICAL.BRONZE.CHAINLIT_FEEDBACKS
                    WHERE ID = :id
                """),
                {
                    "id": feedback_id
                },
            )

        return True
