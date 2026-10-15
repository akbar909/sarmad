# DeepGuard - AI Fake Product Detection System

DeepGuard is a complete production-ready full-stack web application built for a Final Year Project (FYP). It uses a Convolutional Neural Network (CNN) alongside Large Language Models (LLMs like Anthropic Claude or OpenAI GPT) to identify fake or counterfeit products from uploaded images and provide detailed explanations to the user.

## Features
- **User Authentication:** Secure JWT-based login and registration system.
- **Role-Based Access Control:** Distinct Admin and Registered User views.
- **Multimodal AI Detection:** 
  - CNN Model for Image Classification (Genuine vs Fake).
  - LLM Integration for detailed, human-readable explanations.
- **AI Chat Assistant:** Talk to an AI expert about product authentication.
- **Modern UI:** Built with Tailwind CSS and glassmorphism design principles.
- **Admin Dashboard:** Full oversight of users, detection history, and AI API settings.

## Tech Stack
- **Backend:** Python, FastAPI, SQLAlchemy, SQLite (configurable to PostgreSQL/MySQL), PyJWT.
- **Frontend:** HTML5, CSS3, JavaScript (Vanilla), Tailwind CSS, Chart.js, SweetAlert2, Axios.
- **AI / ML:** TensorFlow (Placeholder for `.h5` CNN), Anthropic / OpenAI APIs (Mocked placeholders included).

## Project Structure
- `backend/`: FastAPI source code, database models, AI services, and routing.
- `frontend/`: Static HTML, CSS, and JS files for the UI.

## Getting Started

### Prerequisites
- Python 3.10+
- pip (Python package manager)

### Installation

1. **Clone or Download the Repository**
2. **Navigate to the Backend Directory**
   ```bash
   cd backend
   ```
3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```
4. **Run the Backend Server**
   ```bash
   uvicorn main:app --reload
   ```
   The backend will start at `http://localhost:8000`. Swagger UI docs are available at `http://localhost:8000/docs`.

5. **Serve the Frontend**
   You can use any static file server to serve the frontend. The easiest way is using Python's built-in HTTP server:
   ```bash
   cd ../frontend
   python -m http.server 3000
   ```
   Then open `http://localhost:3000` in your browser.

## Default Admin Account
The very first user registered in the system will automatically be assigned the `admin` role. Subsequent users will be regular `user`s. 

## Next Steps for FYP Deployment
1. Replace `backend/services/cnn_model.py` logic with loading your actual trained `fake_product_model.h5`.
2. Add your Anthropic and OpenAI API keys to `backend/services/claude_service.py` and `openai_service.py` to replace the mock time delays with real HTTP requests.
3. Update `backend/database.py` with your MySQL or PostgreSQL connection string if you prefer it over SQLite.
