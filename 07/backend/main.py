from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base
# Import all models to ensure they are registered with SQLAlchemy
from models import user, detection, report, announcement, api_settings

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="DeepGuard API", description="AI Fake Product Detection System API")

# Setup CORS for frontend to communicate
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For development, allow all
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from routes import auth, admin, detection as detection_route, chat, reports, superadmin

app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(superadmin.router, prefix="/api/superadmin", tags=["Super Admin"])
app.include_router(detection_route.router, prefix="/api/detection", tags=["Detection"])
app.include_router(detection_route.router, prefix="/api/detect", tags=["Detection"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])

@app.get("/")
def root():
    return {"message": "Welcome to DeepGuard API"}

