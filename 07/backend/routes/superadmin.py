from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
from models.user import User
from models.detection import Detection
from models.report import Report
from models.api_settings import APISettings
from utils.auth_utils import SECRET_KEY, ALGORITHM, get_password_hash
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import os
from datetime import datetime, timedelta

router = APIRouter()
security = HTTPBearer()

def get_superadmin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )
        if payload.get("role") != "superadmin":
            raise HTTPException(
                status_code=403,
                detail="Super Admin access required"
            )
        return payload
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )

# 1. USER MANAGEMENT
@router.get("/users")
def get_all_users(
    db: Session = Depends(get_db),
    admin=Depends(get_superadmin)
):
    users = db.query(User).order_by(User.id.asc()).all()
    return [{
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "phone": u.phone or "N/A",
        "role": u.role,
        "is_banned": bool(getattr(u, 'is_banned', False)),
        "plain_password": u.plain_password or "••••••••",
        "created_at": str(u.created_at) if u.created_at else "N/A"
    } for u in users]

@router.put("/users/{user_id}/role")
def change_user_role(
    user_id: int,
    data: dict,
    db: Session = Depends(get_db),
    admin=Depends(get_superadmin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = data.get("role", "user")
    db.commit()
    return {"message": f"Role updated to {user.role}"}

@router.put("/users/{user_id}/ban")
def ban_user(
    user_id: int,
    data: dict,
    db: Session = Depends(get_db),
    admin=Depends(get_superadmin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_banned = data.get("ban", True)
    db.commit()
    action = "banned" if user.is_banned else "unbanned"
    return {"message": f"User {action}"}

@router.put("/users/{user_id}/reset-password")
def reset_password(
    user_id: int,
    data: dict,
    db: Session = Depends(get_db),
    admin=Depends(get_superadmin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    new_pass = data.get("new_password", "DeepGuard@123")
    user.password = get_password_hash(new_pass)
    user.plain_password = new_pass
    db.commit()
    return {"message": "Password reset successful"}

@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin=Depends(get_superadmin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Delete associated detections & reports first for cascade safety
    db.query(Detection).filter(Detection.user_id == user_id).delete()
    db.query(Report).filter(Report.user_id == user_id).delete()
    db.delete(user)
    db.commit()
    return {"message": "User deleted"}

# 2. DETECTION MANAGEMENT
@router.get("/detections")
def get_all_detections(
    db: Session = Depends(get_db),
    admin=Depends(get_superadmin)
):
    detections = db.query(Detection).order_by(Detection.created_at.desc()).all()
    results = []
    for d in detections:
        user = db.query(User).filter(User.id == d.user_id).first()
        results.append({
            "id": d.id,
            "user_id": d.user_id,
            "user_name": user.name if user else "Unknown User",
            "user_email": user.email if user else "N/A",
            "result": d.result,
            "confidence": d.confidence,
            "category": d.category or "General",
            "explanation": d.llm_explanation,
            "created_at": str(d.created_at) if d.created_at else "N/A"
        })
    return results

@router.delete("/detections/{detection_id}")
def delete_detection(
    detection_id: int,
    db: Session = Depends(get_db),
    admin=Depends(get_superadmin)
):
    detection = db.query(Detection).filter(Detection.id == detection_id).first()
    if not detection:
        raise HTTPException(status_code=404, detail="Detection not found")
    db.delete(detection)
    db.commit()
    return {"message": "Detection deleted"}

# 3. ANALYTICS
@router.get("/analytics")
def get_analytics(
    db: Session = Depends(get_db),
    admin=Depends(get_superadmin)
):
    total_users = db.query(User).count()
    total_admins = db.query(User).filter(User.role == "admin").count()
    total_detections = db.query(Detection).count()
    genuine = db.query(Detection).filter(Detection.result.ilike("genuine%")).count()
    fake = db.query(Detection).filter(Detection.result.ilike("fake%")).count()
    
    today = datetime.utcnow().date()
    today_detections = db.query(Detection).filter(
        func.date(Detection.created_at) == today
    ).count()
    
    banned_users = db.query(User).filter(User.is_banned == True).count()

    return {
        "total_users": total_users,
        "total_admins": total_admins,
        "total_detections": total_detections,
        "genuine_count": genuine,
        "fake_count": fake,
        "today_detections": today_detections,
        "banned_users": banned_users
    }

# 4. REPORTS MANAGEMENT
@router.get("/reports")
def get_all_reports(
    db: Session = Depends(get_db),
    admin=Depends(get_superadmin)
):
    reports = db.query(Report).order_by(Report.created_at.desc()).all()
    results = []
    for r in reports:
        user = db.query(User).filter(User.id == r.user_id).first()
        results.append({
            "id": r.id,
            "user_id": r.user_id,
            "user_name": user.name if user else "Anonymous",
            "user_email": user.email if user else "N/A",
            "product_name": r.product_name,
            "category": r.category,
            "description": r.description,
            "status": r.status or "pending",
            "created_at": str(r.created_at) if r.created_at else "N/A"
        })
    return results

@router.put("/reports/{report_id}/status")
def update_report_status(
    report_id: int,
    data: dict,
    db: Session = Depends(get_db),
    admin=Depends(get_superadmin)
):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    report.status = data.get("status", "reviewed")
    db.commit()
    return {"message": "Status updated"}

@router.delete("/reports/{report_id}")
def delete_report(
    report_id: int,
    db: Session = Depends(get_db),
    admin=Depends(get_superadmin)
):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    db.delete(report)
    db.commit()
    return {"message": "Report deleted"}

from models.announcement import Announcement

# ADMIN CREATION & LIST
@router.get("/admins")
def get_all_admins(
    db: Session = Depends(get_db),
    admin=Depends(get_superadmin)
):
    admins = db.query(User).filter(User.role == "admin").order_by(User.id.asc()).all()
    return [{
        "id": a.id,
        "name": a.name,
        "email": a.email,
        "phone": a.phone or "N/A",
        "is_banned": bool(getattr(a, 'is_banned', False)),
        "plain_password": a.plain_password or "••••••••",
        "created_at": str(a.created_at) if a.created_at else "N/A"
    } for a in admins]

@router.post("/admins")
def create_admin(
    data: dict,
    db: Session = Depends(get_db),
    admin=Depends(get_superadmin)
):
    name = data.get("name")
    email = data.get("email")
    password = data.get("password")

    if not name or not email or not password:
        raise HTTPException(status_code=400, detail="Name, email, and password are required")
    
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="User with this email already exists")

    new_admin = User(
        name=name,
        email=email,
        password=get_password_hash(password),
        plain_password=password,
        role="admin",
        is_banned=False
    )
    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)
    return {"message": "Admin account created successfully", "id": new_admin.id}

# ANNOUNCEMENTS
@router.get("/announcements")
def get_announcements(
    db: Session = Depends(get_db),
    admin=Depends(get_superadmin)
):
    announcements = db.query(Announcement).order_by(Announcement.created_at.desc()).all()
    return [{
        "id": a.id,
        "title": a.title,
        "message": a.message,
        "type": getattr(a, 'type', 'info') or 'info',
        "sent_to": getattr(a, 'sent_to', 'all') or 'all',
        "created_at": str(a.created_at) if a.created_at else "N/A"
    } for a in announcements]

@router.post("/announcements")
def create_announcement(
    data: dict,
    db: Session = Depends(get_db),
    admin=Depends(get_superadmin)
):
    title = data.get("title")
    message = data.get("message")
    ann_type = data.get("type", "info")
    sent_to = data.get("sent_to", "all")

    if not title or not message:
        raise HTTPException(status_code=400, detail="Title and message are required")

    ann = Announcement(
        title=title,
        message=message,
        type=ann_type,
        sent_to=sent_to
    )
    db.add(ann)
    db.commit()
    db.refresh(ann)
    return {"message": "Announcement published successfully", "id": ann.id}

@router.delete("/announcements/{id}")
def delete_announcement(
    id: int,
    db: Session = Depends(get_db),
    admin=Depends(get_superadmin)
):
    ann = db.query(Announcement).filter(Announcement.id == id).first()
    if not ann:
        raise HTTPException(status_code=404, detail="Announcement not found")
    db.delete(ann)
    db.commit()
    return {"message": "Announcement deleted"}

# SYSTEM INFO & DANGER ZONE
@router.get("/system-info")
def get_system_info(
    db: Session = Depends(get_db),
    admin=Depends(get_superadmin)
):
    # Calculate database size for SQLite if local
    db_size = "2.4 MB"
    db_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "deepguard.db")
    if os.path.exists(db_file):
        size_bytes = os.path.getsize(db_file)
        db_size = f"{size_bytes / (1024 * 1024):.2f} MB"
    
    return {
        "database_size": db_size,
        "total_storage": "14.2 MB",
        "system_uptime": "99.98%",
        "version": "DeepGuard v1.0",
        "active_model": "Groq Vision Qwen 3.6 27B",
        "groq_key_set": bool(os.getenv("GROQ_API_KEY")),
        "gemini_key_set": bool(os.getenv("GEMINI_API_KEY")),
        "openrouter_key_set": bool(os.getenv("OPENROUTER_API_KEY"))
    }

@router.post("/settings")
def update_settings(
    data: dict,
    admin=Depends(get_superadmin)
):
    env_path = ".env"
    
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            lines = f.readlines()
    else:
        lines = []
    
    updates = {}
    if data.get("groq_key"):
        updates["GROQ_API_KEY"] = data["groq_key"]
    if data.get("gemini_key"):
        updates["GEMINI_API_KEY"] = data["gemini_key"]
    if data.get("openrouter_key"):
        updates["OPENROUTER_API_KEY"] = data["openrouter_key"]
    if data.get("anthropic_key"):
        updates["ANTHROPIC_API_KEY"] = data["anthropic_key"]
    
    if not updates:
        raise HTTPException(
            status_code=400,
            detail="No API key provided to update"
        )
    
    new_lines = []
    updated_keys = set()
    
    for line in lines:
        matched = False
        for key, value in updates.items():
            if line.strip().startswith(key + "="):
                new_lines.append(f"{key}={value}\n")
                updated_keys.add(key)
                matched = True
                break
        if not matched:
            new_lines.append(line)
    
    # Add any keys that didn't already exist in the file
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}\n")
    
    with open(env_path, 'w') as f:
        f.writelines(new_lines)
    
    # Reload environment so the change takes effect 
    # without restarting the server
    from dotenv import load_dotenv
    load_dotenv(override=True)
    
    return {"message": "API keys updated successfully. Restart the server for changes to fully take effect."}

@router.post("/danger/clear-detections")
def clear_all_detections(
    db: Session = Depends(get_db),
    admin=Depends(get_superadmin)
):
    count = db.query(Detection).delete()
    db.commit()
    return {"message": f"Successfully cleared {count} detection logs."}

@router.post("/danger/reset-db")
def reset_database(
    db: Session = Depends(get_db),
    admin=Depends(get_superadmin)
):
    # Clears detections & reports, keeps users & admins
    det_count = db.query(Detection).delete()
    rep_count = db.query(Report).delete()
    ann_count = db.query(Announcement).delete()
    db.commit()
    return {"message": f"Database reset complete. Cleared {det_count} scans, {rep_count} reports, and {ann_count} announcements. User accounts preserved."}

