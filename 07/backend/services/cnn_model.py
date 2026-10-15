import openai
import base64
import json
import os
import io
from dotenv import load_dotenv
from PIL import Image
import numpy as np
try:
    from scipy import ndimage
except ImportError:
    ndimage = None

load_dotenv()

def check_image_quality(image_bytes):
    """Runs BEFORE any AI call. Rejects unusable 
    photos early so we never waste an API call or 
    guess on a bad image."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img_gray = img.convert('L')
        img_array = np.array(img_gray)

        width, height = img.size
        if width < 100 or height < 100:
            return (False,
                "Image resolution is too low. Please "
                "upload a larger, clearer photo.")

        if ndimage is not None:
            laplacian = ndimage.laplace(img_array.astype(float))
            blur_score = laplacian.var()
        else:
            # Pure numpy Laplacian approximation if scipy is not installed
            gy, gx = np.gradient(img_array.astype(float))
            gxx = np.gradient(gx, axis=1)
            gyy = np.gradient(gy, axis=0)
            laplacian = gxx + gyy
            blur_score = laplacian.var()

        print(f"[QUALITY] Blur score: {blur_score:.2f} (rejected if under 8)")
        if blur_score < 8:
            return (False,
                "This image appears blurry. Please hold "
                "the camera steady and retake in focus.")

        avg_brightness = np.mean(img_array)
        if avg_brightness < 30:
            return (False,
                "This image is too dark. Please retake "
                "with better lighting.")
        if avg_brightness > 240:
            return (False,
                "This image is overexposed. Please "
                "retake with normal lighting.")

        return (True, "OK")
    except Exception:
        return (False,
            "Could not read this image file. Please "
            "upload a valid JPG or PNG photo.")


def honest_failure_response(reason="unknown"):
    print(f"[FALLBACK] All AI failed, reason: {reason}")
    return (
        "Indeterminate",
        0.0,
        "Analysis could not be completed: no AI provider returned a usable result. No verdict was made.",
        "Unknown"
    )


def extract_real_verdict(thinking_text):
    """Reads the model's OWN concluding statement 
    from its reasoning instead of guessing."""
    lower = thinking_text.lower()
    conclusion_zone = lower[-400:]

    fake_signals = [
        "is fake", "is a fake", "counterfeit",
        "not genuine", "not authentic",
        "appears to be fake", "likely fake",
        "signs of being fake"
    ]
    genuine_signals = [
        "is genuine", "appears genuine", "authentic",
        "looks real", "consistent with official",
        "matches the official", "no signs of",
        "legitimate"
    ]

    fake_hit = any(s in conclusion_zone for s in fake_signals)
    genuine_hit = any(s in conclusion_zone for s in genuine_signals)

    if fake_hit and not genuine_hit:
        result, confidence = "Fake", 80.0
    elif genuine_hit and not fake_hit:
        result, confidence = "Genuine", 85.0
    else:
        fake_count = sum(lower.count(s) for s in fake_signals)
        genuine_count = sum(lower.count(s) for s in genuine_signals)
        if genuine_count > fake_count:
            result, confidence = "Genuine", 78.0
        elif fake_count > genuine_count:
            result, confidence = "Fake", 78.0
        else:
            return honest_failure_response("inconclusive reasoning")

    category = "General"
    if any(w in lower for w in
           ["phone","iphone","samsung","realme",
            "charger","earphone","laptop","smartphone"]):
        category = "Electronics"
    elif any(w in lower for w in
             ["shoe","sneaker","nike","adidas","boot"]):
        category = "Footwear"
    elif any(w in lower for w in
             ["tablet","syrup","pill","medicine","supplement"]):
        category = "Medicine"
    elif any(w in lower for w in
             ["lipstick","perfume","cream","makeup","cosmetic"]):
        category = "Cosmetics"

    sentences = thinking_text.replace("\n", " ").split(". ")
    explanation = ""
    for s in reversed(sentences):
        s = s.strip()
        if 40 < len(s) < 180 and any(
            w in s.lower() for w in genuine_signals + fake_signals
        ):
            explanation = s + "."
            break
    if not explanation:
        explanation = f"Identified as {category} product based on visual analysis."

    print(f"[VERDICT-FROM-THINKING] {result} {confidence}% {category}")
    return (result, confidence, explanation, category)


def parse_response(text):
    text = text.strip()
    if not text:
        return honest_failure_response(
            "AI service returned no response"
        )

    json_text = text
    if "<think>" in text and "</think>" in text:
        after_think = text.split("</think>")[-1].strip()
        if after_think and "{" in after_think:
            json_text = after_think
        else:
            thinking = text.split("<think>")[1].split("</think>")[0]
            return extract_real_verdict(thinking)

    if "```json" in json_text:
        json_text = json_text.split("```json")[1].split("```")[0].strip()
    elif "```" in json_text:
        json_text = json_text.split("```")[1].strip()

    start = json_text.find("{")
    end = json_text.rfind("}")
    if start == -1 or end == -1:
        return honest_failure_response(
            "AI did not return a valid response"
        )

    try:
        data = json.loads(json_text[start:end+1])
        result = data.get("result")
        if result not in ["Genuine", "Fake"]:
            return honest_failure_response("invalid result in AI response")
        confidence = float(data.get("confidence", 75))
        category = data.get("category", "General")
        explanation = data.get("explanation", "Analysis complete.")
        return (result, confidence, explanation, category)
    except Exception:
        if "<think>" in text:
            return extract_real_verdict(text)
        return honest_failure_response("could not parse AI response")


def predict_image(image_bytes, image_type="image/jpeg", category=None):
    # STEP 0: quality gate BEFORE calling any AI
    is_clear, quality_message = check_image_quality(image_bytes)
    if not is_clear:
        print(f"[QUALITY CHECK FAILED] {quality_message}")
        return ("Unclear Image", 0.0, quality_message, "Unknown")

    print("[QUALITY CHECK] Passed - proceeding to AI analysis")

    # Guarded hook for local ML models (enabled via USE_LOCAL_MODELS=true)
    if os.getenv("USE_LOCAL_MODELS", "false").lower() in ("true", "1", "yes"):
        try:
            from services.local_models import predict_local
            local_res = predict_local(image_bytes, category_hint=category)
            if local_res and isinstance(local_res, dict):
                print("[FINAL] Provider used: local-model")
                return (
                    str(local_res.get("result", "Genuine")),
                    float(local_res.get("confidence", 80.0)),
                    str(local_res.get("explanation", "Local model prediction complete.")),
                    str(local_res.get("category", "Footwear"))
                )
        except Exception as e:
            print(f"[LOCAL MODEL HOOK ERROR] {e}")

    # Convert to JPEG for compatibility
    from PIL import Image as PILImage
    try:
        img = PILImage.open(io.BytesIO(image_bytes))
        if img.mode != 'RGB':
            img = img.convert('RGB')
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=85)
        image_bytes = buf.getvalue()
        image_type = "image/jpeg"
    except Exception as e:
        print(f"[IMAGE CONVERT] {e}")

    image_base64 = base64.standard_b64encode(image_bytes).decode()

    prompt_text = """Respond with ONLY the JSON object below. 
Do not think out loud. Do not explain. Do not use 
<think> tags. Your entire response must start with { 
and end with }. Nothing else.

You are DeepGuard AI, a product authentication expert.
Identify the product category: Electronics, Footwear, 
Medicine, or Cosmetics. Determine Genuine or Fake based 
on logo quality, packaging, build quality. Give benefit 
of doubt - professional product photos are usually genuine.

{"result":"Genuine","confidence":85,"category":"Electronics","explanation":"Brief reason under 30 words","red_flags":[],"positive_signs":["reason"]}"""

    from groq import Groq

    try:
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        response = client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are DeepGuard AI, a product authentication expert.\n"
                        "Identify the product category (Electronics, Footwear, Medicine, or Cosmetics).\n"
                        "Determine if Genuine or Fake based on logo quality, packaging, stitching, and build details.\n"
                        "You MUST respond ONLY with a raw valid JSON object in this exact format:\n"
                        '{"result": "Genuine", "confidence": 88.0, "category": "Footwear", "explanation": "Brief explanation under 30 words"}'
                    )
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                        {"type": "text", "text": "Authenticate this product. Respond with JSON only."}
                    ]
                }
            ],
            max_tokens=250,
            temperature=0.1
        )
        response_text = response.choices[0].message.content
        print(f"[GROQ] Response length: {len(response_text)}")
        result = parse_response(response_text)
        print(f"[FINAL] Provider used: groq")
        if result[0] not in ("Could Not Determine", "Indeterminate"):
            return result
    except Exception as e:
        print(f"[GROQ ERROR] {e}")

    try:
        fallback_client = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY")
        )
        response = fallback_client.chat.completions.create(
            model="google/gemini-2.0-flash-thinking-exp:free",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                    {"type": "text", "text": prompt_text}
                ]
            }],
            max_tokens=400,
            temperature=0
        )
        response_text = response.choices[0].message.content
        print(f"[OPENROUTER] Response length: {len(response_text)}")
        print(f"[FINAL] Provider used: openrouter")
        return parse_response(response_text)
    except Exception as e:
        print(f"[OPENROUTER ERROR] {e}")

    print(f"[FINAL] Provider used: none (all failed)")
    return honest_failure_response("all AI services unavailable")


