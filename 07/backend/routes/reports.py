from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models.report import Report
from models.user import User
from routes.detection import get_current_user

router = APIRouter()

@router.post("/submit")
def submit_report(
    report_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    report = Report(
        user_id=current_user.id,
        product_name=report_data.get("product_name"),
        # We need to map category from the model schema
        description=report_data.get("description"),
        product_url=report_data.get("product_url"),
        status="Pending"
    )
    db.add(report)
    db.commit()
    return {"message": "Report submitted successfully"}

@router.get("/all")
def get_all_reports(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    reports = db.query(Report).order_by(Report.created_at.desc()).all()
    return reports
