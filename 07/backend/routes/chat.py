from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import get_db
from models.user import User
from routes.detection import get_current_user
from groq import Groq
import os
import json
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

SYSTEM_PROMPT = """You are DeepGuard AI Assistant, an expert product authentication specialist with 20 years of experience detecting counterfeit products.

Your expertise covers:
1. FOOTWEAR: Nike, Adidas, Puma, Bata authentication
   - Stitching quality, logo placement, sole analysis
   
2. ELECTRONICS: Phones, chargers, earphones, cables
   - Build quality, logo clarity, port alignment
   
3. MEDICINE: Tablets, syrups, supplements
   - Packaging integrity, holograms, batch numbers
   
4. COSMETICS: Perfumes, creams, makeup
   - Bottle quality, label alignment, serial numbers

You can:
- Answer questions about fake product detection
- Give specific tips for each category
- Explain how to verify product authenticity
- Discuss common counterfeit patterns
- Help users understand detection results

Rules:
- Give DIFFERENT responses based on what user asks
- Be specific and helpful
- Never give generic responses
- If asked about yourself, explain you are DeepGuard AI powered by advanced AI
- Respond in same language as user (English or Urdu/Roman Urdu)
- Keep responses concise but informative"""

@router.post("/message")
async def chat_message(
    message: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    user_message = message.get("message", "").strip() or message.get("prompt", "").strip()
    chat_history = message.get("history", [])
    
    if not user_message:
        raise HTTPException(
            status_code=400, 
            detail="Message cannot be empty"
        )
    
    print(f"[CHAT] User {current_user.name}: {user_message}")
    
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        raise HTTPException(
            status_code=500,
            detail="AI service not configured. GROQ_API_KEY is missing."
        )
    
    try:
        client = Groq(api_key=groq_key)
        
        # Build messages with history
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        
        # Add chat history (last 10 messages)
        for msg in chat_history[-10:]:
            role = msg.get("role", "user")
            if role not in ["system", "user", "assistant"]:
                role = "user"
            messages.append({
                "role": role,
                "content": msg.get("content", "")
            })
        
        # Add current message
        messages.append({
            "role": "user",
            "content": user_message
        })
        
        # Try models in fallback order
        models_to_try = [
            "qwen/qwen3.6-27b",
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "openai/gpt-oss-20b"
        ]
        
        completion = None
        last_error = None
        for model_name in models_to_try:
            try:
                completion = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    max_tokens=1024,
                    temperature=0.7,
                    stream=False
                )
                if completion and completion.choices:
                    break
            except Exception as me:
                last_error = me
                print(f"[CHAT MODEL WARN] Model {model_name} failed: {str(me)}")
        
        if not completion or not completion.choices:
            raise last_error or Exception("No completion choices returned from Groq API.")

        response_text = completion.choices[0].message.content
        
        # Remove thinking tags if present
        if "<think>" in response_text:
            response_text = response_text.split("</think>")[-1].strip()
        
        print(f"[CHAT] Response ({len(response_text)} chars): {response_text[:100]}")
        
        return {
            "response": response_text,
            "reply": response_text,
            "status": "success"
        }
        
    except Exception as e:
        print(f"[CHAT ERROR] {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"AI Error: {str(e)}"
        )

@router.get("/history")
async def get_chat_history(
    current_user: User = Depends(get_current_user)
):
    return {"history": [], "status": "success"}
