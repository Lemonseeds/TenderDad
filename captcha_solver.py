import base64
import re
import time
import os
from groq import Groq
from config import VISION_MODELS

# --- Groq Client for Vision ---
client = Groq()


def solve_captcha(page, image_selector: str = 'img#captchaImage') -> str:
    """
    Screenshots the CAPTCHA image on a portal page and uses the
    vision LLM to read the distorted text.
    
    Accepts an optional `image_selector` (defaults to standard GePNIC 'img#captchaImage')
    """
    try:
        captcha_img = page.locator(image_selector)

        if captcha_img.count() == 0:
            print("[CAPTCHA] Could not find CAPTCHA image element.")
            return ""

        # Screenshot just the CAPTCHA element as bytes
        img_bytes = captcha_img.screenshot()
        
        # Convert to base64 for the vision LLM
        img_b64 = base64.b64encode(img_bytes).decode('utf-8')

        for model_name in VISION_MODELS:
            try:
                # Ask Groq to read the CAPTCHA
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an OCR tool. Output only the raw characters you see. No thinking, no explanation."
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{img_b64}"
                                    }
                                },
                                {
                                    "type": "text",
                                    "text": "Read the CAPTCHA. Reply with ONLY the characters (4-6 alphanumeric). Nothing else."
                                }
                            ]
                        }
                    ],
                    temperature=0,
                    max_tokens=50
                )
                
                raw_text = response.choices[0].message.content.strip()
                
                # Robustly remove <think> blocks (even if truncated)
                if "</think>" in raw_text:
                    text = raw_text.split("</think>")[-1].strip()
                else:
                    # If there's no closing tag, standard regex removal
                    text = re.sub(r'<think>.*', '', raw_text, flags=re.DOTALL).strip()
                    if not text and not raw_text.startswith("<think>"):
                        text = raw_text
                
                # SANITIZE: GePNIC CAPTCHAs are strictly alphanumeric.
                text = re.sub(r'[^a-zA-Z0-9]', '', text)
                
                print(f"[CAPTCHA] Vision LLM ({model_name}) read: '{text}' (Raw: '{raw_text}')")
                
                # GePNIC CAPTCHAs are typically 5 or 6 characters long.
                # Reject obviously wrong outputs (too short or way too long).
                if len(text) < 4 or len(text) > 8:
                    print(f"[CAPTCHA] Model {model_name} returned invalid length ({len(text)}). Discarding...")
                    continue
                    
                return text
                
            except Exception as model_err:
                err_str = str(model_err).lower()
                if any(code in err_str for code in ["429", "503", "400", "capacity", "rate limit", "rate_limit", "limit"]):
                    print(f"[CAPTCHA] Model {model_name} hit rate limit. Trying next model...")
                    continue
                else:
                    raise model_err
                    
        # All models exhausted for this attempt
        return ""

    except Exception as e:
        print(f"[CAPTCHA] Error solving CAPTCHA: {e}")
        return ""

