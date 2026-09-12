from playwright.sync_api import sync_playwright
from captcha_solver import solve_captcha
from config import CAPTCHA_MAX_RETRIES, MAX_PAGES


def scrape_cppp_master(portal_name: str, portal_url: str, keyword: str = "HVAC") -> list[dict]:
    """
    Scraper for the CPPP Master Portal Aggregator (eprocure.gov.in/cppp)
    This site aggregates from all GePNIC state/central portals, so it
    finds way more results. It has a slightly different DOM than standard GePNIC.
    """
    print(f"\n{'='*60}")
    print(f"  Scraping: {portal_name}")
    print(f"  Keyword:  {keyword}")
    print(f"{'='*60}")
    
    tenders = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        print(f"[{portal_name}] Navigating...")
        page.goto(portal_url, timeout=60000)
        
        try:
            # 1. Wait for search box (id="skeyword")
            page.wait_for_selector("input#skeyword", timeout=15000)
            
            # 2. Type keyword
            page.locator("input#skeyword").fill(keyword)
            print(f"[{portal_name}] Typed '{keyword}' into search box.")
            
            # 3. Solve CAPTCHA
            print(f"[{portal_name}] Attempting to auto-solve CAPTCHA...")
            captcha_solved = False

            for attempt in range(1, CAPTCHA_MAX_RETRIES + 1):
                print(f"[{portal_name}] CAPTCHA attempt {attempt} of {CAPTCHA_MAX_RETRIES}...")

                # CPPP Master uses a different CAPTCHA image tag
                captcha_text, raw_img_bytes = solve_captcha(page, image_selector='img[src*="image-captcha-generate"]')

                if not captcha_text:
                    print(f"[{portal_name}] Failed to read CAPTCHA. Retrying...")
                    page.reload()
                    page.wait_for_selector("input#skeyword", timeout=15000)
                    page.locator("input#skeyword").fill(keyword)
                    continue

                print(f"[{portal_name}] Guessed CAPTCHA: '{captcha_text}'")
                
                # Verify the keyword is still in the search box before submitting
                current_keyword = page.locator('input#skeyword').input_value()
                if current_keyword.strip() != keyword:
                    print(f"[{portal_name}] Keyword was cleared! Re-filling '{keyword}'...")
                    page.locator('input#skeyword').fill(keyword)

                # Fill CAPTCHA and submit
                page.locator('input#edit-captcha-response').fill(captcha_text)
                
                # The submit button is #btnSearch
                page.locator('input#btnSearch').click()
                print(f"[{portal_name}] Clicked Search.")

                # Wait for page to respond
                page.wait_for_timeout(4000)

                # Check if CAPTCHA failed by looking for the error message
                error_exists = page.locator('text="The answer you entered for the CAPTCHA was not correct."').count() > 0
                
                if error_exists:
                    print(f"[{portal_name}] Attempt {attempt} failed (incorrect CAPTCHA). Retrying...")
                    # The page might have reloaded, so re-fill the keyword
                    page.wait_for_selector("input#skeyword", timeout=15000)
                    page.locator("input#skeyword").fill(keyword)
                else:
                    print(f"[{portal_name}] CAPTCHA solved! Search successful.")
                    
                    # Be smart: Save the successfully solved CAPTCHA to a dataset folder
                    dataset_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "captcha_dataset")
                    os.makedirs(dataset_dir, exist_ok=True)
                    filename = f"{captcha_text}_{int(time.time()*1000)}.png"
                    with open(os.path.join(dataset_dir, filename), 'wb') as f:
                        f.write(raw_img_bytes)
                    
                    captcha_solved = True
                    break

            if not captcha_solved:
                print(f"\n[{portal_name}] Auto-solve failed after {CAPTCHA_MAX_RETRIES} attempts.")
                print(f"[{portal_name}] Reopening browser in VISIBLE mode so you can solve the CAPTCHA manually...\n")

                # Close the headless browser
                browser.close()

                # Relaunch as VISIBLE so the user can see the page
                browser = p.chromium.launch(headless=False)
                page = browser.new_page()
                page.goto(portal_url, timeout=60000)
                page.wait_for_selector("input#skeyword", timeout=15000)
                page.locator("input#skeyword").fill(keyword)

                print(f"[{portal_name}] Browser is now visible. Please:")
                print(f"  1. Solve the CAPTCHA in the browser window")
                print(f"  2. Click 'Search'")
                print(f"  3. Come back here and press ENTER")
                input("\nPress ENTER after you've solved the CAPTCHA and results have loaded...")

            # 4. Scrape Results
            print(f"[{portal_name}] Scraping results...")
            
            # If there are no results, the portal usually displays a message.
            if page.locator("text=/No Records Found/i").count() > 0 or \
                 page.locator("text=/Nothing found/i").count() > 0 or \
                 page.locator("text=/No Tenders/i").count() > 0 or \
                 page.locator("text=/No active tenders/i").count() > 0:
                print(f"[{portal_name}] No tenders found for keyword '{keyword}'. Returning empty list.")
                return tenders
            
            # Base URL is https://eprocure.gov.in
            base_url = "https://eprocure.gov.in"
            
            # Create snapshot directory
            import os
            snapshot_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tender_snapshots")
            os.makedirs(snapshot_dir, exist_ok=True)
            
            page_num = 1
            
            while True:
                print(f"[{portal_name}] Scraping page {page_num}...")
                page.wait_for_selector('table tbody tr', timeout=15000)
                
                rows = page.query_selector_all('table tbody tr')
                print(f"[{portal_name}] Found {len(rows)} tenders on page {page_num}!")
                
                for row in rows:
                    cells = row.query_selector_all('td')
                    if len(cells) >= 5:
                        # Col 2 (index 2) contains the closing/bid submission end date
                        closing_date = cells[2].inner_text().strip() if len(cells) > 2 else ""

                        # Col 4 (index 4) contains title and link
                        title_cell = cells[4]
                        title = title_cell.inner_text().strip()
                        link_el = title_cell.query_selector('a')
                        href = link_el.get_attribute("href") if link_el else ""
                        
                        if href and not href.startswith("http"):
                            href = base_url + href

                        # Extract tender_id: use the link text (before the slash separator) as ID
                        tender_id = link_el.inner_text().strip() if link_el else ""
                        
                        # Col 5 = Organisation
                        organisation = cells[5].inner_text().strip() if len(cells) > 5 else ""
                        
                        if title:
                            tenders.append({
                                "tender_title": title,
                                "raw_tender_text": title,
                                "link": href,  # temporary — will be replaced with PDF path
                                "source": portal_name,
                                "closing_date": closing_date,
                                "tender_id": tender_id,
                                "organisation": organisation,
                                "tender_value": "",
                                "_detail_href": href,  # internal: used for PDF snapshot
                            })
                
                # Check pagination
                if page_num >= MAX_PAGES:
                    print(f"[{portal_name}] Reached page limit ({MAX_PAGES}). Stopping pagination.")
                    break

                next_btn = page.locator('.pagination a:has-text("Next")')
                if next_btn.count() > 0:
                    print(f"[{portal_name}] 'Next' page found. Clicking...")
                    next_btn.first.click()
                    page.wait_for_timeout(4000)
                    page_num += 1
                else:
                    break
            
            # 5. Capture HTML snapshots of tender detail pages
            import re
            print(f"[{portal_name}] Capturing snapshots for {len(tenders)} tenders...")
            for i, t in enumerate(tenders):
                detail_href = t.pop("_detail_href", "")
                if not detail_href:
                    continue
                    
                safe_id = re.sub(r'[^\w\-]', '_', t.get('tender_id', f'tender_{i}'))
                html_path = os.path.join(snapshot_dir, f"{safe_id}.html")
                
                # Skip if we already have a snapshot for this tender
                if os.path.exists(html_path):
                    t["link"] = html_path
                    print(f"  [{i+1}/{len(tenders)}] Snapshot already exists: {safe_id}.html")
                    continue
                
                try:
                    page.goto(detail_href, timeout=30000)
                    page.wait_for_timeout(3000)
                    
                    # Save an HTML snapshot of the page content
                    html_content = page.content()
                    with open(html_path, 'w', encoding='utf-8') as f:
                        f.write(html_content)
                    t["link"] = html_path
                    print(f"  [{i+1}/{len(tenders)}] Saved: {safe_id}.html")
                except Exception as e:
                    print(f"  [{i+1}/{len(tenders)}] Failed to capture {safe_id}: {e}")
                    # Keep the original href as fallback
                
        except Exception as e:
            print(f"[{portal_name}] Error while scraping: {e}")
            
        page.wait_for_timeout(2000)
        browser.close()
        
    print(f"[{portal_name}] Done. Scraped {len(tenders)} tenders.\n")
    return tenders

