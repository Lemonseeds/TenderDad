"""
TenderDad — Automated Tender Scraping & Classification Pipeline
Built for Axenic Systems (HVAC & Clean Room specialists)

Scrapes GePNIC-based tender portals, auto-solves CAPTCHAs using vision AI,
and classifies tenders using LangGraph + LLM.
"""

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Force UTF-8 encoding for Windows terminal to prevent UnicodeEncodeError
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from config import PORTALS, SEARCH_KEYWORDS
from scrapers.gepnic import scrape_gepnic
from scrapers.cppp_master import scrape_cppp_master
from pipeline import app
from vector_db import ingest_pdfs
from reporter import generate_pdf_digest, send_email_digest


def _scrape_one(portal: dict, keyword: str) -> list[dict]:
    """Scrape a single portal+keyword combination."""
    if portal.get("type") == "cppp_master":
        return scrape_cppp_master(
            portal_name=portal["name"],
            portal_url=portal["url"],
            keyword=keyword,
        )
    else:
        return scrape_gepnic(
            portal_name=portal["name"],
            portal_url=portal["url"],
            keyword=keyword,
        )


def scrape_all_portals() -> list[dict]:
    """Scrape all configured portals one by one."""
    all_tenders = []

    # Build the list of (portal, keyword) jobs
    jobs = [(portal, keyword) for portal in PORTALS for keyword in SEARCH_KEYWORDS]
    total = len(jobs)

    print(f"\n⚡ {total} scraping jobs, running one by one...\n")
    start = time.perf_counter()

    for i, (portal, keyword) in enumerate(jobs, 1):
        label = f"{portal['name']} / {keyword}"
        print(f"\n[{i}/{total}] {label}")
        try:
            tenders = _scrape_one(portal, keyword)
            all_tenders.extend(tenders)
            print(f"  ✓ {label} — {len(tenders)} tenders")
        except Exception as e:
            print(f"  ✗ {label} — FAILED: {e}")

    elapsed = time.perf_counter() - start
    print(f"\n⚡ All {total} jobs finished in {elapsed:.1f}s  ({len(all_tenders)} tenders total)\n")

    return all_tenders


def run_pipeline(tenders: list[dict]) -> list[dict]:
    """Feed each scraped tender through the LangGraph scoring pipeline.
    Returns a list of approved tenders from this run."""
    approved_tenders = []
    
    if not tenders:
        print("\nNo tenders found across all portals. Nothing to process.")
        return approved_tenders
    
    print(f"\n{'='*60}")
    print(f"  PIPELINE: Scoring {len(tenders)} tenders via Vector DB")
    print(f"{'='*60}\n")
    
    for i, tender in enumerate(tenders, 1):
        print(f"[{i}/{len(tenders)}] {tender['tender_title'][:80]}...")
        print(f"  Source: {tender['source']} | Link: {tender.get('link', 'N/A')}")
        
        final_state = app.invoke({
            "tender_title": tender["tender_title"],
            "raw_tender_text": tender["raw_tender_text"],
            "link": tender.get("link", ""),
            "source": tender.get("source", ""),
            "closing_date": tender.get("closing_date", ""),
            "tender_id": tender.get("tender_id", ""),
            "organisation": tender.get("organisation", ""),
            "tender_value": tender.get("tender_value", ""),
        })
        
        if final_state.get("is_relevant") and not final_state.get("is_duplicate"):
            # Update the original tender dict with scores for reporting
            tender["confidence_score"] = final_state.get("confidence_score")
            tender["fit_category"] = final_state.get("fit_category")
            approved_tenders.append(tender)
            
        print("-" * 50)
        
    return approved_tenders


if __name__ == "__main__":
    # 1. Ingest company PDFs into vector DB (skips if already done)
    print("=" * 60)
    print("  STEP 1: Preparing Vector Database")
    print("=" * 60)
    ingest_pdfs()
    
    # 2. Scrape all portals
    print("\n" + "=" * 60)
    print("  STEP 2: Scraping Tender Portals")
    print("=" * 60)
    scraped_tenders = scrape_all_portals()
    
    # 3. Run through LangGraph scoring pipeline
    print("\n" + "=" * 60)
    print("  STEP 3: Scoring Tenders")
    print("=" * 60)
    approved_tenders = run_pipeline(scraped_tenders)
    
    # 4. Reporting
    print("\n" + "=" * 60)
    print("  STEP 4: Reporting")
    print("=" * 60)
    if approved_tenders:
        print(f"Found {len(approved_tenders)} approved tenders today. Generating PDF digest...")
        pdf_path = generate_pdf_digest(approved_tenders)
        print(f"PDF created at: {pdf_path}")
        send_email_digest(pdf_path, approved_tenders)
    else:
        print("No new approved tenders today. Skipping report.")
    
    print("\n✓ Pipeline complete.")