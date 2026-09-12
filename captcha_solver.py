import re
import easyocr

# --- Initialize EasyOCR ---
# Load the model globally so it's only initialized once in memory.
# We explicitly set verbose=False to hide initialization warnings.
print("[CAPTCHA] Initializing EasyOCR Reader (this may take a moment)...")
reader = easyocr.Reader(['en'], gpu=False, verbose=False)

def solve_captcha(page, image_selector: str = 'img#captchaImage') -> str:
    """
    Screenshots the CAPTCHA image on a portal page and uses EasyOCR
    to read the distorted text.
    
    Args:
        page: The Playwright page object.
        image_selector: CSS selector for the CAPTCHA image.
        
    Returns:
        str: The sanitized CAPTCHA text, or an empty string on failure.
    """
    try:
        captcha_img = page.locator(image_selector)

        if captcha_img.count() == 0:
            print("[CAPTCHA] Could not find CAPTCHA image element.")
            return ""

        # Screenshot just the CAPTCHA element as bytes
        img_bytes = captcha_img.screenshot()
        
        # Execute local OCR
        # We use an allowlist to heavily restrict output to alphanumeric chars,
        # which dramatically increases accuracy on noisy GePNIC captchas.
        results = reader.readtext(
            img_bytes,
            allowlist='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
            detail=0,
            paragraph=True
        )
        
        if not results:
            print("[CAPTCHA] EasyOCR returned no text.")
            return ""
            
        # Combine any fragmented text blocks
        raw_text = "".join(results)
        
        # SANITIZE: GePNIC CAPTCHAs are strictly alphanumeric.
        text = re.sub(r'[^a-zA-Z0-9]', '', raw_text)
        
        print(f"[CAPTCHA] EasyOCR read: '{text}' (Raw: '{raw_text}')")
        
        # GePNIC CAPTCHAs are typically 5 or 6 characters long.
        # Reject obviously wrong outputs (too short or way too long).
        if len(text) < 4 or len(text) > 8:
            print(f"[CAPTCHA] EasyOCR returned invalid length ({len(text)}). Discarding...")
            return ""
            
        return text

    except Exception as e:
        print(f"[CAPTCHA] Error solving CAPTCHA: {e}")
        return ""

