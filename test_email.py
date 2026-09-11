import sqlite3
from reporter import generate_pdf_digest, send_email_digest

def test_email():
    conn = sqlite3.connect("tenders.db")
    cursor = conn.cursor()
    cursor.execute("SELECT title, source, link, confidence_score, fit_category FROM processed_tenders WHERE status = 'approved'")
    rows = cursor.fetchall()
    
    if not rows:
        print("No approved tenders found in the database. Generating some dummy ones for the test...")
        # Add dummy data if the DB was cleared or no approved tenders exist
        approved_tenders = [
            {
                "tender_title": "HVAC work for clean room construction",
                "source": "CPPP Master Portal (Aggregator)",
                "link": "https://eprocure.gov.in/cppp/",
                "confidence_score": 93.7,
                "fit_category": "Good Fit"
            },
            {
                "tender_title": "Supply and installation of AHU and ducting system",
                "source": "Kerala eTenders",
                "link": "https://etenders.kerala.gov.in/",
                "confidence_score": 95.5,
                "fit_category": "Good Fit"
            },
            {
                "tender_title": "Chiller plant installation for hospital",
                "source": "CPPP Master Portal (Aggregator)",
                "link": "https://eprocure.gov.in/cppp/",
                "confidence_score": 65.8,
                "fit_category": "Medium Fit"
            }
        ]
    else:
        approved_tenders = []
        for row in rows:
            approved_tenders.append({
                "tender_title": row[0],
                "source": row[1],
                "link": row[2],
                "confidence_score": row[3],
                "fit_category": row[4]
            })
        
    print(f"Found {len(approved_tenders)} approved tenders for the digest.")
    print("Generating PDF...")
    pdf_path = generate_pdf_digest(approved_tenders)
    
    print(f"Sending email with attached PDF ({pdf_path})...")
    send_email_digest(pdf_path)
    print("Done!")
    
if __name__ == "__main__":
    test_email()
