
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from chainlit.utils import mount_chainlit
from html import escape

from auth import register_user

app = FastAPI()


# ---------------------------------------
# Landing page
# ---------------------------------------

@app.get("/", response_class=HTMLResponse)
async def home():

    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Medical Test Assistant</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">

        <style>
            body {
                font-family: Arial, sans-serif;
                background: #101827;
                color: white;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
            }

            .card {
                background: #1e293b;
                padding: 40px;
                border-radius: 18px;
                width: 340px;
                text-align: center;
            }

            .logo {
                font-size: 48px;
            }

            p {
                color: #94a3b8;
            }

            a {
                display: block;
                padding: 14px;
                margin-top: 16px;
                border-radius: 8px;
                text-decoration: none;
                font-weight: bold;
            }

            .login {
                background: #2563eb;
                color: white;
            }

            .register {
                background: #16a34a;
                color: white;
            }
        </style>
    </head>

    <body>
        <div class="card">

            <div class="logo">🩺</div>

            <h2>Medical Test Assistant</h2>

            <p>
                Understand and analyze your medical
                test results using AI.
            </p>

            <a class="login" href="/chat">
                Sign In
            </a>

            <a class="register" href="/register">
                Create Account
            </a>

            <p>Secure access to your personal test results.</p>

        </div>
    </body>
    </html>
    """


# ---------------------------------------
# Registration page
# ---------------------------------------

@app.get("/register", response_class=HTMLResponse)
async def register_page():

    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Create Account</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">

        <style>
            body {
                font-family: Arial, sans-serif;
                background: #101827;
                color: white;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
            }

            .card {
                background: #1e293b;
                padding: 32px;
                border-radius: 14px;
                width: 340px;
            }

            input {
                box-sizing: border-box;
                width: 100%;
                padding: 12px;
                margin: 9px 0;
                border-radius: 6px;
                border: 1px solid #475569;
                background: #0f172a;
                color: white;
            }

            button {
                width: 100%;
                padding: 13px;
                margin-top: 15px;
                background: #16a34a;
                color: white;
                border: none;
                border-radius: 6px;
                cursor: pointer;
            }

            a { color: #4ade80; }
        </style>
    </head>

    <body>
        <div class="card">

            <h2>🩺 Create Account</h2>

            <p>Join Medical Test Assistant</p>

            <form action="/register" method="post">

                <input
                    name="full_name"
                    placeholder="Full Name"
                    maxlength="255"
                    required
                >

                <input
                    name="email"
                    type="email"
                    placeholder="Email Address"
                    maxlength="255"
                    required
                >

                <input
                    name="password"
                    type="password"
                    placeholder="Password (10+ characters)"
                    minlength="10"
                    required
                >

                <input
                    name="confirm_password"
                    type="password"
                    placeholder="Confirm Password"
                    required
                >

                <button type="submit">
                    Create Account
                </button>

            </form>

            <p>Already have an account?
                <a href="/chat">Sign In</a>
            </p>

        </div>
    </body>
    </html>
    """


# ---------------------------------------
# Handle registration
# ---------------------------------------

@app.post("/register")
async def register(
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...)
):

    if password != confirm_password:
        return HTMLResponse(
            "Passwords do not match. <a href='/register'>Try again</a>",
            status_code=400
        )

    success, message = register_user(
        full_name,
        email,
        password
    )

    if success:
        return RedirectResponse(
            url="/chat",
            status_code=303
        )

    return HTMLResponse(
        f"{escape(message)} <a href='/register'>Try again</a>",
        status_code=400
    )


# ---------------------------------------
# Mount Chainlit
# ---------------------------------------

mount_chainlit(
    app=app,
    target="snowapp.py",
    path="/chat"
)
