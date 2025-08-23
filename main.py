from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import requests, os, jwt, datetime
from pydantic import BaseModel
import json

# ----------------------------
# 🔹 CONFIG
# ----------------------------
from dotenv import load_dotenv
load_dotenv()

# Google OAuth credentials from environment variables
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "<YOUR_GOOGLE_CLIENT_ID>")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "<YOUR_GOOGLE_CLIENT_SECRET>")
REDIRECT_URI = os.getenv("REDIRECT_URI", "https://womensafety-backend-app.onrender.com/auth/callback")

# JWT secret key
SECRET_KEY = os.getenv("SECRET_KEY", "supersecret")

# ----------------------------
# 🔹 INIT
# ----------------------------
app = FastAPI()

# Enable CORS for the frontend application
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this to your frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------
# 🔹 MODELS
# ----------------------------
class User(BaseModel):
    email: str
    name: str
    google_id: str
    picture: str | None = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: User

# ----------------------------
# 🔹 UTILS
# ----------------------------
def get_google_auth_url():
    """Builds the Google OAuth authorization URL."""
    return (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"response_type=code&client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        "&scope=openid%20email%20profile"
        "&access_type=offline"
    )

def exchange_code_for_token(auth_code: str):
    """Exchanges the authorization code for an access token."""
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": auth_code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    response = requests.post(token_url, data=data)
    response.raise_for_status()
    return response.json()

def get_google_user_info(access_token: str):
    """Fetches user information from Google."""
    user_info_url = "https://www.googleapis.com/oauth2/v2/userinfo"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(user_info_url, headers=headers)
    response.raise_for_status()
    return response.json()

def create_jwt(user_id: str) -> str:
    """Creates a JWT token for the user."""
    payload = {
        "sub": user_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def verify_jwt(token: str):
    """Verifies and decodes a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ----------------------------
# 🔹 ROUTES
# ----------------------------
@app.get("/")
def read_root():
    return {"message": "Welcome to the Women Safety App Backend!"}

@app.get("/auth/login")
def login():
    """Step 1: Redirect user to Google OAuth."""
    return RedirectResponse(get_google_auth_url())

@app.get("/auth/callback")
def callback(code: str):
    """Step 2: Handle the Google OAuth callback, get user info, and return JWT."""
    try:
        token_data = exchange_code_for_token(code)
        access_token = token_data.get("access_token")
        user_info = get_google_user_info(access_token)

        user = User(
            email=user_info["email"],
            name=user_info["name"],
            google_id=user_info["id"],
            picture=user_info.get("picture")
        )

        jwt_token = create_jwt(user.google_id)

        # Return a JSON response with the user data and token
        return JSONResponse(content={
            "token": jwt_token,
            "user": user.dict()
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Authentication failed: {e}")

@app.post("/auth/login/mobile")
def mobile_login(id_token: str):
    """Handles login from the mobile app by receiving the Google ID token."""
    try:
        # Verify ID token with Google
        user_info_url = "https://oauth2.googleapis.com/tokeninfo"
        response = requests.get(user_info_url, params={"id_token": id_token})
        response.raise_for_status()
        user_info = response.json()

        user = User(
            email=user_info["email"],
            name=user_info.get("name", ""),  # name may not always be in token
            google_id=user_info["sub"],
            picture=user_info.get("picture")
        )

        # Create your own backend JWT (for protected routes)
        jwt_token = create_jwt(user.google_id)

        return JSONResponse(content={
            "token": jwt_token,
            "user": user.dict()
        })

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid ID token or authentication error: {e}")

from fastapi import Depends

@app.get("/protected")
def protected_route(token: str = Depends(verify_jwt)):
    return {"message": "You are authenticated!", "user_id": token}
