from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel
from pymongo import MongoClient
from bson import ObjectId
import os
from datetime import datetime
from typing import Optional
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Women Safety App API",
    description="Backend API for Shakti Women Safety App",
    version="1.0.0"
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your frontend domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GZip compression for faster responses
app.add_middleware(GZipMiddleware, minimum_size=1000)

# MongoDB connection with error handling
try:
    MONGODB_URI = os.getenv("MONGODB_URI")
    if not MONGODB_URI:
        raise ValueError("MONGODB_URI environment variable is required")
    
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    db = client["women_safety_app"]
    users_collection = db["users"]
    
    # Test connection
    client.admin.command('ping')
    logger.info("Successfully connected to MongoDB")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {e}")
    raise

# Get Google Client ID from environment variable
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
if not GOOGLE_CLIENT_ID:
    logger.warning("GOOGLE_CLIENT_ID environment variable is not set")

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
        if not GOOGLE_CLIENT_ID:
            raise HTTPException(status_code=500, detail="Google authentication not configured")
            
        # Verify the token
        id_info = id_token.verify_oauth2_token(
            token, google_requests.Request(), GOOGLE_CLIENT_ID
        )
        
        # Check if token is issued by Google
        if id_info['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            raise ValueError('Wrong issuer.')
            
        return id_info
    except ValueError as e:
        logger.warning(f"Invalid Google token: {e}")
        raise HTTPException(status_code=400, detail="Invalid Google token")
    except Exception as e:
        logger.error(f"Google token verification error: {e}")
        raise HTTPException(status_code=500, detail="Authentication service error")

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
            logger.info(f"User logged in: {user_data['email']}")
            return {"message": "Login successful", "user": existing_user}
        else:
            # Create new user
            user_data["created_at"] = datetime.utcnow()
            result = users_collection.insert_one(user_data)
            new_user = users_collection.find_one({"_id": result.inserted_id})
            new_user["_id"] = str(new_user["_id"])
            logger.info(f"New user created: {user_data['email']}")
            return {"message": "User created successfully", "user": new_user}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

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
        logger.error(f"Get user error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/")
async def root():
    return {"message": "Women Safety App API is running", "status": "healthy"}

@app.get("/health")
async def health_check():
    try:
        # Check database connection
        client.admin.command('ping')
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

# Add startup event
@app.on_event("startup")
async def startup_event():
    logger.info("Starting Women Safety App API server")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)