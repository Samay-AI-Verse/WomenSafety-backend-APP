from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient
from bson import ObjectId
import os
from datetime import datetime
from typing import Optional
import requests
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import json

app = FastAPI(title="Women Safety App API")

# CORS middleware to allow Flutter app to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your app's domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB connection
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
client = MongoClient(MONGODB_URI)
db = client["women_safety_app"]
users_collection = db["users"]

# Get Google Client ID from environment variable
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "your_google_client_id_here")

# Models
class User(BaseModel):
    google_id: str
    email: str
    name: str
    profile_picture: Optional[str] = None
    created_at: datetime = datetime.utcnow()
    last_login: Optional[datetime] = None

class GoogleSignInRequest(BaseModel):
    id_token: str

# Helper function to verify Google ID token
def verify_google_token(token: str):
    try:
        # Verify the token
        id_info = id_token.verify_oauth2_token(
            token, google_requests.Request(), GOOGLE_CLIENT_ID
        )
        
        # Check if token is issued by Google
        if id_info['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            raise ValueError('Wrong issuer.')
            
        return id_info
    except ValueError:
        # Invalid token
        raise HTTPException(status_code=400, detail="Invalid Google token")

# Routes
@app.post("/api/auth/google")
async def google_auth(request: GoogleSignInRequest):
    try:
        # Verify Google token
        user_info = verify_google_token(request.id_token)
        
        # Extract user data
        user_data = {
            "google_id": user_info["sub"],
            "email": user_info["email"],
            "name": user_info.get("name", ""),
            "profile_picture": user_info.get("picture"),
            "last_login": datetime.utcnow()
        }
        
        # Check if user already exists
        existing_user = users_collection.find_one({"google_id": user_data["google_id"]})
        
        if existing_user:
            # Update last login time
            users_collection.update_one(
                {"_id": existing_user["_id"]},
                {"$set": {"last_login": datetime.utcnow()}}
            )
            # Convert ObjectId to string for JSON serialization
            existing_user["_id"] = str(existing_user["_id"])
            return {"message": "Login successful", "user": existing_user}
        else:
            # Create new user
            user_data["created_at"] = datetime.utcnow()
            result = users_collection.insert_one(user_data)
            new_user = users_collection.find_one({"_id": result.inserted_id})
            new_user["_id"] = str(new_user["_id"])
            return {"message": "User created successfully", "user": new_user}
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Authentication failed: {str(e)}")

@app.get("/api/users/{user_id}")
async def get_user(user_id: str):
    try:
        user = users_collection.find_one({"_id": ObjectId(user_id)})
        if user:
            user["_id"] = str(user["_id"])
            return user
        else:
            raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/")
async def root():
    return {"message": "Women Safety App API is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)