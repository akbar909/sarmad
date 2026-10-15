from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from models.user import User
from models.user_otp import UserOTP
from utils.auth_utils import verify_password, get_password_hash, create_access_token
from utils.email_utils import send_otp_email
from pydantic import BaseModel, EmailStr
from typing import Optional
import random
import os
from datetime import datetime, timedelta

router = APIRouter()

class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str
    phone: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
    user_id: int
    name: str

@router.post("/register")
def register(user_data: UserRegister, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user_data.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user_data.password)
    # the first user will be admin
    is_first = db.query(User).count() == 0
    role = "admin" if is_first else "user"
    
    new_user = User(
        name=user_data.name,
        email=user_data.email,
        password=hashed_password,
        plain_password=user_data.password,
        phone=user_data.phone,
        role=role
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "User created successfully", "user_id": new_user.id, "role": role}

@router.post("/login", response_model=Token)
def login(user_data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == user_data.email).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid email or password")
    
    if getattr(user, 'is_banned', False):
        raise HTTPException(status_code=403, detail="Your account has been suspended/banned by an administrator.")

    if not verify_password(user_data.password, user.password):
        raise HTTPException(status_code=400, detail="Invalid email or password")
    
    access_token = create_access_token(data={"sub": user.email, "role": user.role, "id": user.id})
    return {"access_token": access_token, "token_type": "bearer", "role": user.role, "user_id": user.id, "name": user.name, "email": user.email}

# Admin login (can use same endpoint, but frontend enforces /admin/login view)
@router.post("/admin-login", response_model=Token)
def admin_login(user_data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == user_data.email).first()
    if not user or not verify_password(user_data.password, user.password):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    
    if getattr(user, 'is_banned', False):
        raise HTTPException(status_code=403, detail="Your account has been suspended/banned by an administrator.")

    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized as admin")
        
    access_token = create_access_token(data={"sub": user.email, "role": user.role, "id": user.id})
    return {"access_token": access_token, "token_type": "bearer", "role": user.role, "user_id": user.id, "name": user.name, "email": user.email}

SUPER_ADMIN_EMAIL = "superadmin@deepguard.com"
SUPER_ADMIN_PASSWORD = "DeepGuard@2025"

@router.post("/superadmin-login")
def superadmin_login(credentials: dict):
    email = credentials.get("email")
    password = credentials.get("password")

    if email == SUPER_ADMIN_EMAIL and password == SUPER_ADMIN_PASSWORD:
        token = create_access_token(data={
            "sub": SUPER_ADMIN_EMAIL,
            "role": "superadmin",
            "id": -1
        })
        return {
            "access_token": token,
            "token_type": "bearer",
            "role": "superadmin",
            "name": "Super Administrator",
            "email": SUPER_ADMIN_EMAIL
        }
    else:
        raise HTTPException(
            status_code=401,
            detail="Invalid super admin credentials"
        )


class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp_code: str
    new_password: str

@router.post("/forgot-password")
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(status_code=400, detail="This email is not registered with us.")

    otp = f"{random.randint(100000, 999999)}"
    expiry = datetime.utcnow() + timedelta(minutes=10)

    db_otp = db.query(UserOTP).filter(UserOTP.email == request.email).first()
    if db_otp:
        db_otp.otp_code = otp
        db_otp.expires_at = expiry
    else:
        db_otp = UserOTP(email=request.email, otp_code=otp, expires_at=expiry)
        db.add(db_otp)

    db.commit()

    print(f"\n[FORGOT PASSWORD] Sending OTP {otp} to {request.email}")
    print(f"[EMAIL_USER from env] {os.getenv('EMAIL_USER')}")
    result = send_otp_email(request.email, otp)
    print(f"[EMAIL RESULT] Sent: {result}\n")

    return {"message": "OTP code has been sent to your email. Please check your inbox or server logs."}

@router.post("/reset-password")
def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    db_otp = db.query(UserOTP).filter(UserOTP.email == request.email).first()
    if not db_otp:
        raise HTTPException(status_code=400, detail="No active password reset request found for this email.")
    
    if db_otp.otp_code != request.otp_code:
        raise HTTPException(status_code=400, detail="Invalid OTP code. Please try again.")
    
    if db_otp.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="OTP code has expired. Please request a new one.")
    
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(status_code=400, detail="User associated with this email no longer exists.")
    
    hashed_password = get_password_hash(request.new_password)
    user.password = hashed_password
    
    db.delete(db_otp)
    db.commit()
    
    return {"message": "Your password has been reset successfully. You can now login with your new password."}
