from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from models.user import User
from models.detection import Detection
from models.report import Report
from models.api_settings import APISettings
from utils.auth_utils import SECRET_KEY, ALGORITHM
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import os

router = APIRouter()
security = HTTPBearer()

def get_current_admin(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("id")
        role = payload.get("role")
        if role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

@router.get("/dashboard-stats")
def get_dashboard_stats(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    total_users = db.query(User).count()
    total_detections = db.query(Detection).count()
    total_reports = db.query(Report).count()
    
    fake_count = db.query(Detection).filter(Detection.result.ilike("fake%")).count()
    genuine_count = db.query(Detection).filter(Detection.result.ilike("genuine%")).count()
    
    return {
        "total_users": total_users,
        "total_detections": total_detections,
        "total_reports": total_reports,
        "fake_ratio": {"fake": fake_count, "genuine": genuine_count}
    }

@router.get("/users")
def get_all_users(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [{
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "phone": u.phone or "N/A",
        "password": u.plain_password or "••••••••",
        "role": u.role,
        "created_at": u.created_at
    } for u in users]

@router.get("/detections")
def get_all_detections(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    detections = db.query(Detection).order_by(Detection.created_at.desc()).all()
    results = []
    for d in detections:
        user = db.query(User).filter(User.id == d.user_id).first()
        results.append({
            "id": d.id,
            "user_name": user.name if user else "Unknown User",
            "user_email": user.email if user else "unknown@deepguard.com",
            "image_url": d.image_url,
            "category": d.category or "General",
            "result": d.result,
            "confidence": d.confidence,
            "llm_explanation": d.llm_explanation,
            "created_at": d.created_at
        })
    return results

@router.get("/settings")
def get_settings(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    api_setting = db.query(APISettings).first()
    if not api_setting:
        return {
            "llm_provider": "groq",
            "anthropic_key": os.getenv("ANTHROPIC_API_KEY", ""),
            "openai_key": os.getenv("OPENAI_API_KEY", ""),
            "groq_key": os.getenv("GROQ_API_KEY", "")
        }
    return {
        "llm_provider": api_setting.llm_provider or "groq",
        "anthropic_key": api_setting.anthropic_key or os.getenv("ANTHROPIC_API_KEY", ""),
        "openai_key": api_setting.openai_key or os.getenv("OPENAI_API_KEY", ""),
        "groq_key": api_setting.groq_key or os.getenv("GROQ_API_KEY", "")
    }

@router.post("/settings/update")
def update_settings(
    settings: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    api_setting = db.query(APISettings).first()
    if not api_setting:
        api_setting = APISettings()
        db.add(api_setting)
    
    if "anthropic_key" in settings and settings["anthropic_key"]:
        api_setting.anthropic_key = settings["anthropic_key"]
    if "openai_key" in settings and settings["openai_key"]:
        api_setting.openai_key = settings["openai_key"]
    if "groq_key" in settings and settings["groq_key"]:
        api_setting.groq_key = settings["groq_key"]
    if "llm_provider" in settings and settings["llm_provider"]:
        api_setting.llm_provider = settings["llm_provider"]
    
    db.commit()
    db.refresh(api_setting)

    # Optional: Update .env file if key is present
    try:
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                env_content = f.read()
            
            if settings.get("groq_key"):
                if "GROQ_API_KEY=" in env_content:
                    lines = env_content.splitlines()
                    new_lines = []
                    for line in lines:
                        if line.startswith("GROQ_API_KEY="):
                            new_lines.append(f"GROQ_API_KEY={settings['groq_key']}")
                        else:
                            new_lines.append(line)
                    env_content = "\n".join(new_lines) + "\n"
                else:
                    env_content += f"\nGROQ_API_KEY={settings['groq_key']}\n"
                
                os.environ["GROQ_API_KEY"] = settings["groq_key"]

            if settings.get("anthropic_key"):
                os.environ["ANTHROPIC_API_KEY"] = settings["anthropic_key"]
            if settings.get("openai_key"):
                os.environ["OPENAI_API_KEY"] = settings["openai_key"]

            with open(env_path, "w", encoding="utf-8") as f:
                f.write(env_content)
    except Exception as e:
        print(f"[SETTINGS .ENV UPDATE WARNING] {str(e)}")

    return {"message": "Settings saved successfully", "status": "success"}

