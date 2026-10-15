from fastapi.security import HTTPBearer 
security = HTTPBearer() 
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models.user import User
from models.detection import Detection
from models.api_settings import APISettings
from datetime import datetime
import json
import jwt
from utils.auth_utils import SECRET_KEY, ALGORITHM
from services.cnn_model import predict_image

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
async def upload_image(
    file: UploadFile = File(...), 
    category: str = Form(None),
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    try:
        # Validate content type
        image_type = file.content_type or "image/jpeg"
        if not image_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="File must be an image (JPG, PNG, etc.)")
        
        image_bytes = await file.read()
        
        print(f"[UPLOAD] User: {current_user.id} | File: {file.filename} | Size: {len(image_bytes)} bytes | Type: {image_type} | Category hint: {category}")

        # Check file is not empty
        if len(image_bytes) == 0:
            raise HTTPException(status_code=400, detail="Empty file uploaded. Please select a valid image.")
        
        image_url = f"/uploads/mock_{file.filename}"
        
        try:
            result, confidence, explanation, detected_category = predict_image(image_bytes, image_type, category=category)
        except Exception as e:
            print(f"[AI MODEL ERROR] {str(e)}")
            raise HTTPException(status_code=500, detail=f"AI Model Error: {str(e)}")
        
        needs_retake = (result == "Unclear Image")
        is_honest_failure = (result == "Could Not Determine")

        # Use AI-detected category; fall back to user hint if AI returned nothing
        final_category = detected_category or category or "General"

        if result == "Genuine":
            risk_level = "LOW"
            recommendation = "Product appears genuine. Safe to purchase."
        elif result == "Fake":
            risk_level = "HIGH"
            recommendation = "Counterfeit indicators detected. Exercise caution and verify authenticity."
        elif result == "Unclear Image":
            risk_level = "UNKNOWN"
            recommendation = explanation
        else:
            risk_level = "UNKNOWN"
            recommendation = "Could not reach a definitive conclusion. Try retaking with a clearer angle or better lighting."

        try:
            # Save to database
            detection = Detection(
                user_id=current_user.id,
                image_url=image_url,
                result=result,
                confidence=float(confidence),
                llm_explanation=explanation,
                category=final_category,
                risk_level=risk_level,
                evidence=json.dumps({}),
                recommendation=recommendation,
                red_flags=json.dumps([]),
                positive_signs=json.dumps([]),
                created_at=datetime.utcnow()
            )
            db.add(detection)
            db.commit()
            db.refresh(detection)
        except Exception as e:
            db.rollback()
            print(f"[DB SAVE ERROR] {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save detection: {str(e)}"
            )
        
        print(f"[UPLOAD SUCCESS] Detection ID: {detection.id} | Result: {result} | Confidence: {confidence}% | Category: {final_category}")

        return {
            "id": detection.id,
            "result": result,
            "confidence": confidence,
            "category": final_category,
            "explanation": explanation,
            "needs_retake": needs_retake,
            "is_honest_failure": is_honest_failure,
            "risk_level": risk_level,
            "recommendation": recommendation,
            "image_url": image_url
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[UPLOAD UNEXPECTED ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=f"Detection process error: {str(e)}")


@router.get("/history")
def get_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    history = db.query(Detection).filter(
        Detection.user_id == current_user.id
    ).order_by(
        Detection.created_at.desc()
    ).all()
    
    results = []
    for d in history:
        try:
            ev = json.loads(d.evidence) if d.evidence else {}
        except Exception:
            ev = {}
        try:
            rf = json.loads(d.red_flags) if d.red_flags else []
        except Exception:
            rf = []
        try:
            ps = json.loads(d.positive_signs) if d.positive_signs else []
        except Exception:
            ps = []

        results.append({
            "id": d.id,
            "result": d.result,
            "confidence": d.confidence,
            "risk_level": getattr(d, "risk_level", "UNKNOWN") or "UNKNOWN",
            "category": d.category,
            "explanation": d.llm_explanation,
            "recommendation": getattr(d, "recommendation", "") or "",
            "evidence": ev,
            "red_flags": rf,
            "positive_signs": ps,
            "created_at": str(d.created_at),
            "image_url": d.image_url
        })
    return results

@router.get("/{detection_id}")
def get_detection_detail(
    detection_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    detection = db.query(Detection).filter(
        Detection.id == detection_id,
        Detection.user_id == current_user.id
    ).first()
    
    if not detection:
        raise HTTPException(
            status_code=404,
            detail="Detection not found"
        )
    
    try:
        ev = json.loads(detection.evidence) if detection.evidence else {}
    except Exception:
        ev = {}
    try:
        rf = json.loads(detection.red_flags) if detection.red_flags else []
    except Exception:
        rf = []
    try:
        ps = json.loads(detection.positive_signs) if detection.positive_signs else []
    except Exception:
        ps = []

    return {
        "id": detection.id,
        "result": detection.result,
        "confidence": detection.confidence,
        "risk_level": getattr(detection, "risk_level", "UNKNOWN") or "UNKNOWN",
        "category": detection.category,
        "explanation": detection.llm_explanation,
        "recommendation": getattr(detection, "recommendation", "") or "",
        "evidence": ev,
        "red_flags": rf,
        "positive_signs": ps,
        "created_at": str(detection.created_at),
        "image_url": detection.image_url
    }
