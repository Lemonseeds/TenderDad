import re
import base64
import threading
import time
import ddddocr
from groq import Groq
from config import VISION_MODELS

# --- Groq Client for Vision Fallback ---
client = Groq()

# --- Initialize ddddocr Ensemble ---
print("[CAPTCHA] Initializing ddddocr ensemble...")
ocr_default = ddddocr.DdddOcr(show_ad=False)
ocr_old = ddddocr.DdddOcr(old=True, show_ad=False)

# Lock to prevent rate limiting from Groq when multiple browsers fallback simultaneously
groq_lock = threading.Lock()

def solve_captcha(page, image_selector: str = 'img#captchaImage') -> tuple[str, bytes]:
    """
    Screenshots the CAPTCHA image and uses a ddddocr ensemble locally.
    If the two models disagree or fail to find 6 characters, it falls back to Groq Vision LLM.
    Returns: (sanitized_captcha_text, raw_image_bytes)
    """
    try:
        captcha_img = page.locator(image_selector)

        if captcha_img.count() == 0:
            print("[CAPTCHA] Could not find CAPTCHA image element.")
            return "", b""

        # 1. Screenshot the CAPTCHA element
        raw_img_bytes = captcha_img.screenshot()
        
        # 2. Local OCR Ensemble
        raw_text_1 = ocr_default.classification(raw_img_bytes)
        raw_text_2 = ocr_old.classification(raw_img_bytes)
        
        # Sanitize (default model outputs lowercase anyway, but old model is mixed case)
        text_1_lower = re.sub(r'[^a-zA-Z0-9]', '', raw_text_1).lower()
        text_2_lower = re.sub(r'[^a-zA-Z0-9]', '', raw_text_2).lower()
        
        # The actual text to submit (preserve case from old model)
        submit_text = re.sub(r'[^a-zA-Z0-9]', '', raw_text_2)
        
        # Exact length 6 and agreement means HIGH CONFIDENCE local solve!
        if len(text_1_lower) == 6 and text_1_lower == text_2_lower:
            print(f"[CAPTCHA] Local CNN High Confidence Solve: '{submit_text}'")
            return submit_text, raw_img_bytes
            
        print(f"[CAPTCHA] Local CNN unconfident (mismatch or bad length). Falling back to Groq Vision LLM...")
        
        # 3. Vision LLM Fallback
        base64_image = base64.b64encode(raw_img_bytes).decode('utf-8')
        
        with groq_lock:
            for model in VISION_MODELS:
                try:
                    print(f"[CAPTCHA] Requesting solve from {model}...")
                    response = client.chat.completions.create(
                        model=model,
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text", 
                                        "text": "Please read the text in this CAPTCHA. The CAPTCHA contains EXACTLY 6 alphanumeric characters. Return ONLY the 6 characters, with absolutely no other text, punctuation, or spaces."
                                    },
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/png;base64,{base64_image}"
                                        }
                                    }
                                ]
                            }
                        ],
                        max_tokens=10,
                        temperature=0.0
                    )
                    
                    raw_guess = response.choices[0].message.content.strip()
                    
                    # If the model uses Chain-of-Thought (like DeepSeek or newer Qwens), 
                    # it outputs <think>...</think>. We must remove everything inside those tags first!
                    raw_guess = re.sub(r'<think>.*?</think>', '', raw_guess, flags=re.DOTALL)
                    
                    guess = re.sub(r'[^a-zA-Z0-9]', '', raw_guess)
                    
                    # Truncate if model hallucinates extra chars
                    if len(guess) > 6:
                        guess = guess[-6:] # Take the LAST 6 characters, in case it said "The answer is ABCDEF"
                        
                    if len(guess) == 6:
                        print(f"[CAPTCHA] Solved via Groq ({model}): '{guess}'")
                        time.sleep(1.5) # Prevent rate limits
                        return guess, raw_img_bytes
                    else:
                        print(f"[CAPTCHA] Groq returned invalid length: '{guess}'. Trying next model...")
                        
                except Exception as e:
                    print(f"[CAPTCHA] Groq model {model} failed: {e}")
                    time.sleep(2)
                    
        return "", b""

    except Exception as e:
        print(f"[CAPTCHA] Error solving CAPTCHA: {e}")
        return "", b""
