from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pymongo import MongoClient
from google.oauth2 import id_token
from google.auth.transport import requests

app = FastAPI()

# MongoDB setup
client = MongoClient("mongodb://localhost:27017/")
db = client["women_safety_app"]
users_collection = db["users"]

# Request body model
class UserLogin(BaseModel):
    id_token: str

@app.post("/auth/login/mobile")
def login_mobile(data: UserLogin):
    try:
        # 🔑 Verify Google ID token
        idinfo = id_token.verify_oauth2_token(
            data.id_token,
            requests.Request(),
            "YOUR_WEB_CLIENT_ID.apps.googleusercontent.com"
        )

        # Extract info
        google_id = idinfo["sub"]
        name = idinfo.get("name")
        email = idinfo.get("email")
        photo = idinfo.get("picture")

        # Store or update user in MongoDB
        user = users_collection.find_one_and_update(
            {"googleId": google_id},
            {"$set": {"name": name, "email": email, "photo": photo}},
            upsert=True,
            return_document=True
        )

        return {"msg": "Login successful", "user": {"name": name, "email": email, "photo": photo}}

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid token: {str(e)}")
