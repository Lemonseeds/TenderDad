import sys
import os
import sqlite3

# Add parent directory to path so we can import from pipeline
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import score_tender

def rescore_all():
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tenders.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT title, confidence_score, fit_category, reasoning, link, source, closing_date, tender_id, organisation, tender_value FROM processed_tenders")
    rows = cursor.fetchall()
    
    print(f"Found {len(rows)} tenders in the database. Rescoring now...\n")
    print("="*80)
    
    for row in rows:
        title, old_score, old_fit, old_reasoning, link, source, closing_date, tender_id, organisation, tender_value = row
        
        state = {
            "tender_title": title,
            "raw_tender_text": "",
            "link": link or "",
            "source": source or "",
            "closing_date": closing_date or "",
            "tender_id": tender_id or "",
            "organisation": organisation or "",
            "tender_value": tender_value or "",
            "is_relevant": False,
            "reasoning": old_reasoning or "",
            "is_duplicate": False,
            "confidence_score": old_score or 0.0,
            "fit_category": old_fit or "",
            "matched_evidence": ""
        }
        
        print(f"TENDER: {title}")
        print(f"[OLD] Fit: {old_fit} | Score: {old_score}")
        
        # To avoid the excessive console logging from score_tender cluttering our diff
        # We will silence it and print the summary.
        original_stdout = sys.stdout
        with open(os.devnull, 'w') as f:
            sys.stdout = f
            try:
                new_result = score_tender(state)
            except Exception as e:
                new_result = {"error": str(e)}
            sys.stdout = original_stdout
            
        if "error" in new_result:
            print(f"[ERROR]: {new_result['error']}")
        else:
            new_score = new_result.get("confidence_score", 0)
            new_fit = new_result.get("fit_category", "Unknown")
            # Safely encode the reasoning to avoid Unicode errors in Windows terminal
            new_reasoning = new_result.get("reasoning", "N/A").encode("ascii", "replace").decode("ascii")
            
            print(f"[NEW] Fit: {new_fit} | Score: {new_score:.2f}%")
            print(f"[NEW REASONING]: {new_reasoning}")
        print("-" * 80)

if __name__ == '__main__':
    rescore_all()
