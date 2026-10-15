from fastapi.security import HTTPBearer 
security = HTTPBearer() 
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models.user import User
from models.detection import Detection
from models.api_settings import APISettings

import jwt
from utils.auth_utils import SECRET_KEY, ALGORITHM
from services.cnn_model import predict_image
from services.claude_service import get_claude_explanation
from services.openai_service import get_openai_explanation

router = APIRouter()

def get_current_user(credentials = Depends(security), db: Session = Depends(get_db)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("id")
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

@router.post("/upload")
async def upload_image(file: UploadFile = File(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    # In a real app, save to Cloudinary or local storage and get URL
    # For now, we mock the image URL
    image_url = f"/uploads/mock_{file.filename}"
    
    # Read file for prediction
    image_bytes = await file.read()
    
    # 1. Run CNN Model
    result, confidence = predict_image(image_bytes)
    
    # 2. Get LLM Provider Setting
    api_setting = db.query(APISettings).first()
    provider = api_setting.llm_provider if api_setting else "claude"
    
    # 3. Get LLM Explanation
    if provider == "claude":
        explanation = get_claude_explanation(result, confidence)
    else:
        explanation = get_openai_explanation(result, confidence)
        
    # 4. Save to Database
    detection = Detection(
        user_id=current_user.id,
        image_url=image_url,
        result=result,
        confidence=confidence,
        llm_explanation=explanation
    )
    db.add(detection)
    db.commit()
    db.refresh(detection)
    
    return {
        "id": detection.id,
        "result": result,
        "confidence": confidence,
        "explanation": explanation,
        "image_url": image_url
    }

@router.get("/history")
def get_history(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    history = db.query(Detection).filter(Detection.user_id == current_user.id).order_by(Detection.created_at.desc()).all()
    return history
