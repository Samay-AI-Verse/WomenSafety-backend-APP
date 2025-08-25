from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pymongo import MongoClient
from google.oauth2 import id_token
from google.auth.transport import requests
import os

app = FastAPI()

# MongoDB Atlas connection (set via Render env var)
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
client = MongoClient(MONGO_URI)
db = client["women_safety_app"]
users_collection = db["users"]

# Google Web Client ID (from Google Cloud Console)
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")

class UserLogin(BaseModel):
    id_token: str

@app.post("/auth/login/mobile")
def login_mobile(data: UserLogin):
    try:
        # ✅ Verify Google ID token with Web Client ID
        idinfo = id_token.verify_oauth2_token(
            data.id_token,
            requests.Request(),
            GOOGLE_CLIENT_ID
        )

        google_id = idinfo["sub"]
        name = idinfo.get("name")
        email = idinfo.get("email")
        photo = idinfo.get("picture")

        # ✅ Store or update user in MongoDB
        users_collection.update_one(
            {"googleId": google_id},
            {"$set": {"name": name, "email": email, "photo": photo}},
            upsert=True
        )

        return {
            "msg": "Login successful",
            "user": {"name": name, "email": email, "photo": photo}
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid token: {str(e)}")
