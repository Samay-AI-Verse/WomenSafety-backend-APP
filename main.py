from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from pymongo import MongoClient
import requests, os, jwt, datetime

# ----------------------------
# 🔹 CONFIG

from dotenv import load_dotenv
load_dotenv()

# ----------------------------
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "<YOUR_GOOGLE_CLIENT_ID>")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "<YOUR_GOOGLE_CLIENT_SECRET>")
REDIRECT_URI = "https://womensafety-backend-app.onrender.com/auth/callback"


SECRET_KEY = os.getenv("SECRET_KEY", "supersecret")
MONGO_URI = os.getenv("MONGO_URI")

# ----------------------------
# 🔹 INIT
# ----------------------------
app = FastAPI()
client = MongoClient(MONGO_URI)
db = client["women_safety_db"]
users = db["users"]

# ----------------------------
# 🔹 MODELS
# ----------------------------
class User(BaseModel):
    email: str
    name: str
    google_id: str
    picture: str | None = None

# ----------------------------
# 🔹 UTILS
# ----------------------------
def create_jwt(user_id: str) -> str:
    payload = {
        "user_id": user_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=1)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def verify_jwt(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None

def get_google_auth_url():
    return (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        "&response_type=code"
        "&scope=openid%20email%20profile"
    )

def exchange_code_for_token(code: str):
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code"
    }
    response = requests.post(token_url, data=data)
    return response.json()

def get_google_user_info(access_token: str):
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    response = requests.get(userinfo_url, params={"access_token": access_token})
    return response.json()

# ----------------------------
# 🔹 ROUTES
# ----------------------------
@app.get("/")
def root():
    return {"msg": "Women Safety API running"}

@app.get("/auth/login")
def login():
    """Step 1: Redirect user to Google OAuth"""
    return RedirectResponse(get_google_auth_url())
from fastapi.responses import RedirectResponse
import urllib.parse, json

@app.get("/auth/callback")
def callback(code: str):
    token_data = exchange_code_for_token(code)
    access_token = token_data.get("access_token")

    user_info = get_google_user_info(access_token)

    user = User(
        email=user_info["email"],
        name=user_info["name"],
        google_id=user_info["id"],
        picture=user_info.get("picture")
    )

    users.update_one({"email": user.email}, {"$set": user.dict()}, upsert=True)

    jwt_token = create_jwt(user.google_id)

    # Encode user info as JSON string for Flutter
    user_json = json.dumps(user.dict())
    params = {
        "token": jwt_token,
        "user": user_json
    }
    redirect_url = f"myapp://login?{urllib.parse.urlencode(params)}"
    return RedirectResponse(redirect_url)

@app.get("/protected")
def protected(token: str):
    """Step 3: Example of protected route"""
    decoded = verify_jwt(token)
    if not decoded:
        return {"error": "Invalid or expired token"}
    return {"msg": "Welcome to protected route!", "decoded": decoded}
