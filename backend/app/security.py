import hashlib, hmac, os
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .database import get_db
from .models import User

SECRET = os.getenv("JWT_SECRET", "local-development-secret-change-before-deployment")
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310000)
    return f"pbkdf2_sha256${salt.hex()}${digest.hex()}"

def verify_password(password: str, encoded: str) -> bool:
    try:
        _, salt, digest = encoded.split("$")
        return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 310000).hex(), digest)
    except ValueError: return False

def token_for(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=int(os.getenv("ACCESS_TOKEN_MINUTES", "720")))
    return jwt.encode({"sub": str(user.id), "role": user.role, "exp": exp}, SECRET, algorithm="HS256")

def current_user(token: str | None = Depends(oauth2), db: Session = Depends(get_db)) -> User:
    if not token: raise HTTPException(401, "Sign in to continue")
    try: payload = jwt.decode(token, SECRET, algorithms=["HS256"]); user_id = int(payload["sub"])
    except Exception: raise HTTPException(401, "Session expired or invalid")
    user = db.get(User, user_id)
    if not user: raise HTTPException(401, "Account not found")
    return user

def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin": raise HTTPException(403, "Administrator access required")
    return user
