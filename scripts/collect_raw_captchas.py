import sys
import os
import time
from playwright.sync_api import sync_playwright

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PORTALS

def collect_raw_captchas(total_target=500):
    dataset_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "captcha_dataset_raw")
    os.makedirs(dataset_dir, exist_ok=True)
    
    # We will distribute the total target evenly across all configured portals
    per_portal_target = total_target // len(PORTALS)
    
    print(f"Collecting ~{per_portal_target} raw CAPTCHAs from each of the {len(PORTALS)} portals...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        for portal in PORTALS:
            portal_name = portal['name']
            url = portal['url']
            
            # Determine the correct image selector based on portal type
            if portal.get('type') == 'cppp_master':
                image_selector = 'img[src*="image-captcha-generate"]'
            else:
                image_selector = 'img#captchaImage'
            
            print(f"\n[{portal_name}] Navigating to {url}...")
            page = browser.new_page()
            
            try:
                page.goto(url, timeout=60000)
                
                count = 0
                while count < per_portal_target:
                    try:
                        # Wait for the captcha image to appear
                        captcha_img = page.locator(image_selector)
                        if captcha_img.count() == 0:
                            print(f"[{portal_name}] CAPTCHA image not found. Reloading...")
                            page.reload()
                            time.sleep(2)
                            continue
                            
                        # Save the raw screenshot
                        raw_bytes = captcha_img.screenshot()
                        filename = f"{portal_name.replace(' ', '_')}_{int(time.time() * 1000)}.png"
                        filepath = os.path.join(dataset_dir, filename)
                        
                        with open(filepath, 'wb') as f:
                            f.write(raw_bytes)
                            
                        count += 1
                        if count % 10 == 0:
                            print(f"[{portal_name}] Collected {count}/{per_portal_target} images...")
                            
                        # Refresh the CAPTCHA
                        # Instead of clicking a refresh button, we can safely just reload the whole page
                        page.reload()
                        # Give it a tiny sleep so we don't hammer their servers too violently
                        time.sleep(0.5)
                        
                    except Exception as e:
                        print(f"[{portal_name}] Error during loop: {e}")
                        page.reload()
                        time.sleep(2)
            
            except Exception as e:
                print(f"[{portal_name}] Failed to load portal: {e}")
            finally:
                page.close()
                
        browser.close()
        
    print(f"\nDone! Raw captchas saved to {dataset_dir}")

if __name__ == "__main__":
    collect_raw_captchas(500)
