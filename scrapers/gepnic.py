import re
from playwright.sync_api import sync_playwright
from captcha_solver import solve_captcha
from config import CAPTCHA_MAX_RETRIES, MAX_PAGES


def scrape_gepnic(portal_name: str, portal_url: str, keyword: str = "HVAC") -> list[dict]:
    """
    Generic scraper for any GePNIC-based tender portal.
    
    Works for Kerala eTenders, CPPP eProcure, and any other state portal
    that runs on the NIC GePNIC platform (they all share the same DOM structure).
    
    Returns a list of dicts:
        {
            "tender_title": str,
            "raw_tender_text": str,
            "link": str,       # URL to the tender detail page
            "source": str      # Which portal it came from
        }
    """
    print(f"\n{'='*60}")
    print(f"  Scraping: {portal_name}")
    print(f"  Keyword:  {keyword}")
    print(f"{'='*60}")
    
    tenders = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        # 1. Navigate to the Active Tenders page
        print(f"[{portal_name}] Navigating...")
        page.goto(portal_url, timeout=60000)
        
        try:
            # 2. Wait for the search form to load
            page.wait_for_selector("input[type='text']", timeout=15000)
            
            # 3. Type the keyword into the Tender Title search box
            search_box = page.locator("input#TenderTitle")
            search_box.fill(keyword)
            print(f"[{portal_name}] Typed '{keyword}' into Tender Title search box.")
            
            # 4. Auto-solve CAPTCHA with retries
            print(f"[{portal_name}] Attempting to auto-solve CAPTCHA...")
            captcha_solved = False

            for attempt in range(1, CAPTCHA_MAX_RETRIES + 1):
                print(f"[{portal_name}] CAPTCHA attempt {attempt} of {CAPTCHA_MAX_RETRIES}...")

                captcha_text = solve_captcha(page)

                if not captcha_text:
                    print(f"[{portal_name}] OCR returned empty. Refreshing CAPTCHA...")
                    if page.locator('button#captcha').count() > 0:
                        page.locator('button#captcha').click()
                        page.wait_for_timeout(1500)
                    continue

                # Fill the CAPTCHA input and click Search
                page.locator('input#captchaText').fill(captcha_text)
                print(f"[{portal_name}] Filled in: '{captcha_text}'")

                page.locator('input#Submit').click()
                print(f"[{portal_name}] Clicked Search.")

                # Wait for page to respond
                page.wait_for_timeout(4000)

                # Check if results loaded
                if page.locator('a[title="View Tender Information"]').count() > 0:
                    print(f"[{portal_name}] CAPTCHA solved! Results loaded.")
                    captcha_solved = True
                    break
                else:
                    print(f"[{portal_name}] Attempt {attempt} failed. Retrying...")
                    
                    # Dismiss any error alert/dialog that may have popped up
                    try:
                        page.on("dialog", lambda dialog: dialog.dismiss())
                    except Exception:
                        pass
                    
                    # Check for error message elements and dismiss them
                    error_ok = page.locator("button:has-text('OK'), button:has-text('Close'), .ui-dialog-buttonset button")
                    if error_ok.count() > 0:
                        error_ok.first.click()
                        page.wait_for_timeout(500)
                    
                    # Clear the CAPTCHA text box
                    captcha_input = page.locator('input#captchaText')
                    if captcha_input.count() > 0:
                        captcha_input.fill("")
                    
                    # Click refresh CAPTCHA button to get a new image
                    if page.locator('button#captcha').count() > 0:
                        page.locator('button#captcha').click()
                        page.wait_for_timeout(1500)

            if not captcha_solved:
                print(f"\n[{portal_name}] Auto-solve failed after {CAPTCHA_MAX_RETRIES} attempts.")
                print(f"[{portal_name}] Reopening browser in VISIBLE mode so you can solve the CAPTCHA manually...\n")

                # Close the headless browser
                browser.close()

                # Relaunch as VISIBLE so the user can see the page
                browser = p.chromium.launch(headless=False)
                page = browser.new_page()
                page.goto(portal_url, timeout=60000)
                page.wait_for_selector("input[type='text']", timeout=15000)
                page.locator("input#TenderTitle").fill(keyword)

                print(f"[{portal_name}] Browser is now visible. Please:")
                print(f"  1. Solve the CAPTCHA in the browser window")
                print(f"  2. Click 'Search'")
                print(f"  3. Come back here and press ENTER")
                input("\nPress ENTER after you've solved the CAPTCHA and results have loaded...")

            # 5. Scrape the results
            print(f"[{portal_name}] Scraping results...")
            
            # Derive the search URL from this specific portal (fixes cross-portal bug)
            # e.g. "https://etenders.kerala.gov.in/nicgep/app?page=FrontEndLatestActiveTenders..."
            #   -> "https://etenders.kerala.gov.in/nicgep/app?page=FrontEndAdvancedSearch&service=page"
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(portal_url)
            search_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', 'page=FrontEndAdvancedSearch&service=page', ''))
            
            # Create snapshot directory
            import os
            snapshot_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tender_snapshots")
            os.makedirs(snapshot_dir, exist_ok=True)
            
            page_num = 1
            
            while True:
                print(f"[{portal_name}] Scraping page {page_num}...")
                page.wait_for_selector('a[title="View Tender Information"]', timeout=15000)
                
                # Walk the table rows that contain tender links
                rows = page.query_selector_all('tr[id^="informal"]')
                print(f"[{portal_name}] Found {len(rows)} tenders on page {page_num}!")
                
                for row in rows:
                    cells = row.query_selector_all('td')
                    if len(cells) < 5:
                        continue
                    
                    # Col 2 = Bid Submission Closing Date
                    closing_date = cells[2].inner_text().strip()
                    
                    # Col 4 = Title cell (contains <a> link + plain text with IDs)
                    title_cell = cells[4]
                    full_text = title_cell.inner_text().strip()
                    
                    link_el = title_cell.query_selector('a[title="View Tender Information"]')
                    title = link_el.inner_text().strip() if link_el else full_text
                    
                    # Extract the session-bound href (we'll use it to capture a PDF snapshot)
                    detail_href = link_el.get_attribute("href") if link_el else ""
                    
                    # Extract tender ID from the text after the link
                    # Format is usually: [RefNo][TenderID] e.g. [AIIMS-JDH/...][2026_AIIMS_925782_1]
                    id_matches = re.findall(r'\[([^\]]+)\]', full_text)
                    tender_id = id_matches[-1] if id_matches else ""
                    
                    # Col 5 = Organisation
                    organisation = cells[5].inner_text().strip() if len(cells) > 5 else ""
                    
                    # Col 6 = Tender Value (if present)
                    tender_value = cells[6].inner_text().strip() if len(cells) > 6 else ""
                    
                    # The link to provide: portal-specific search URL
                    link = search_url
                    
                    if title:
                        tenders.append({
                            "tender_title": full_text,
                            "raw_tender_text": full_text,
                            "link": link,
                            "source": portal_name,
                            "closing_date": closing_date,
                            "tender_id": tender_id,
                            "organisation": organisation,
                            "tender_value": tender_value,
                            "_detail_href": detail_href,  # internal: used for PDF snapshot
                        })
                
                # Check for "Next" button pagination (id="loadNext" on GePNIC portals)
                if page_num >= MAX_PAGES:
                    print(f"[{portal_name}] Reached page limit ({MAX_PAGES}). Stopping pagination.")
                    break

                next_btn = page.locator("a#loadNext")
                if next_btn.count() > 0:
                    print(f"[{portal_name}] 'Next' page found. Clicking...")
                    next_btn.click()
                    # Wait for the next page of results to load
                    page.wait_for_timeout(4000)
                    page_num += 1
                else:
                    break
            
            # 6. Capture HTML snapshots of tender detail pages
            # We still have an active session, so the detail links work right now
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
                    # Navigate to the detail page using the session-bound link
                    if not detail_href.startswith("http"):
                        detail_href = f"{parsed.scheme}://{parsed.netloc}{detail_href}"
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
                    # Keep the search URL as fallback
                
        except Exception as e:
            print(f"[{portal_name}] Error while scraping: {e}")
            
        page.wait_for_timeout(2000)
        browser.close()
        
    print(f"[{portal_name}] Done. Scraped {len(tenders)} tenders.\n")
    return tenders

