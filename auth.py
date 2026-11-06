
import os
import uuid
import bcrypt

from sqlalchemy import text
from snowdb import engine


# --------------------------------------------------
# Password utilities
# --------------------------------------------------

def hash_password(password: str) -> str:

    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password must not exceed 72 UTF-8 bytes.")

    if len(password) < 10:
        raise ValueError("Password must contain at least 10 characters.")

    salt = bcrypt.gensalt(rounds=12)

    return bcrypt.hashpw(
        password.encode("utf-8"),
        salt
    ).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:

    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


# --------------------------------------------------
# Registration
# --------------------------------------------------

def register_user(full_name: str, email: str, password: str):

    email = email.strip().lower()
    full_name = full_name.strip()

    if not full_name or not email:
        return False, "Name and email are required."

    if len(email) > 255 or len(full_name) > 255:
        return False, "Name or email is too long."

    if len(password) > 72:
        return False, "Password is too long."

    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        return False, str(exc)

    user_id = str(uuid.uuid4())

    try:
        with engine.begin() as conn:

            existing = conn.execute(
                text("""
                    SELECT USER_ID
                    FROM MEDICAL.BRONZE.USERS
                    WHERE LOWER(EMAIL) = :email
                    LIMIT 1
                """),
                {"email": email}
            ).first()

            if existing:
                return False, "An account with this email already exists."

            conn.execute(
                text("""
                    INSERT INTO MEDICAL.BRONZE.USERS
                    (
                        USER_ID,
                        AUTH_PROVIDER,
                        AUTH_SUBJECT,
                        EMAIL,
                        FULL_NAME,
                        PASSWORD_HASH,
                        ROLE,
                        IS_ACTIVE
                    )
                    VALUES
                    (
                        :user_id,
                        'LOCAL',
                        :auth_subject,
                        :email,
                        :full_name,
                        :password_hash,
                        'USER',
                        TRUE
                    )
                """),
                {
                    "user_id": user_id,
                    "auth_subject": user_id,
                    "email": email,
                    "full_name": full_name,
                    "password_hash": password_hash
                }
            )

        return True, "Registration successful! You can now sign in."

    except Exception:
        # Log the exception securely on the server.
        return False, "Registration failed. Please try again."


# --------------------------------------------------
# Login
# --------------------------------------------------



def authenticate_user(email: str, password: str):

    email = email.strip().lower()

    try:
        with engine.connect() as conn:

            result = conn.execute(
                text("""
                    SELECT
                        USER_ID,
                        EMAIL,
                        FULL_NAME,
                        PASSWORD_HASH,
                        ROLE,
                        IS_ACTIVE,
                        TENANT_ID,
                        AUTH_PROVIDER
                    FROM MEDICAL.BRONZE.USERS
                    WHERE LOWER(EMAIL) = :email
                      AND AUTH_PROVIDER = 'LOCAL'
                    LIMIT 1
                """),
                {"email": email}
            ).mappings().first()

            if not result:
                print("User not found")
                return None

            # Normalize SQLAlchemy column keys
            user = {
                str(key).upper(): value
                for key, value in result.items()
            }

            print("User found:", user["EMAIL"])
            print("Account active:", user["IS_ACTIVE"])

            # Check account status
            if not user["IS_ACTIVE"]:
                print("Account inactive")
                return None

            # Check password hash
            password_hash = user["PASSWORD_HASH"]

            if not password_hash:
                print("Password hash missing")
                return None

            # Verify password
            if not verify_password(password, password_hash):
                print("Incorrect password")
                return None

            print("LOGIN SUCCESS!")

            return {
                "user_id": user["USER_ID"],
                "email": user["EMAIL"],
                "full_name": user["FULL_NAME"],
                "role": user["ROLE"],
                "tenant_id": user["TENANT_ID"]
            }

    except Exception as e:

        import traceback

        print("\n========== LOGIN ERROR ==========")
        traceback.print_exc()
        print("Error:", repr(e))
        print("================================")

        return None
