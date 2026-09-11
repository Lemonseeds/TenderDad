import os
import zipfile
from datetime import datetime
import smtplib
from email.message import EmailMessage
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
from config import EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT, PORTALS


def generate_html_report(approved_tenders: list[dict]) -> str:
    """Generates a premium, professional HTML layout for the report."""
    
    # Build a mapping of source -> portal base URL
    portal_urls = {}
    for p in PORTALS:
        parsed = urlparse(p["url"])
        portal_urls[p["name"]] = f"{parsed.scheme}://{parsed.netloc}"
        
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg-color: #f8fafc;
                --card-bg: #ffffff;
                --text-main: #0f172a;
                --text-muted: #64748b;
                --accent-blue: #2563eb;
                --border-color: #e2e8f0;
                --good-fit-bg: #dcfce7;
                --good-fit-text: #166534;
                --medium-fit-bg: #fef9c3;
                --medium-fit-text: #854d0e;
            }}
            
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            
            body {{ 
                font-family: 'Inter', sans-serif; 
                color: var(--text-main); 
                background-color: var(--bg-color); 
                padding: 40px; 
                -webkit-font-smoothing: antialiased;
            }}
            
            .report-wrapper {{ 
                max-width: 900px; 
                margin: 0 auto; 
                background: var(--card-bg); 
                border-radius: 12px; 
                box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05), 0 8px 10px -6px rgba(0, 0, 0, 0.01);
                overflow: hidden;
            }}
            
            /* Premium Header */
            .header {{ 
                padding: 40px 50px; 
                background: #0f172a; 
                color: #ffffff;
                display: flex;
                justify-content: space-between;
                align-items: center;
                border-bottom: 4px solid var(--accent-blue);
            }}
            .header-branding h1 {{ 
                font-size: 28px; 
                font-weight: 700; 
                letter-spacing: -0.5px;
                margin-bottom: 6px;
            }}
            .header-branding p {{ 
                font-size: 14px; 
                color: #94a3b8; 
                font-weight: 400;
            }}
            .header-meta {{ text-align: right; }}
            .header-meta .date {{ font-size: 16px; font-weight: 500; color: #f8fafc; }}
            .header-meta .count {{ font-size: 13px; color: #cbd5e1; margin-top: 4px; }}
            
            /* Content Area */
            .content {{ padding: 40px 50px; }}
            
            .intro-text {{
                font-size: 15px;
                color: var(--text-muted);
                line-height: 1.6;
                margin-bottom: 40px;
                padding-bottom: 30px;
                border-bottom: 1px solid var(--border-color);
            }}
            
            /* Tender Cards */
            .tender-list {{ display: flex; flex-direction: column; gap: 30px; }}
            
            .tender-card {{ 
                background: var(--card-bg);
                border: 1px solid var(--border-color);
                border-radius: 8px;
                position: relative;
                page-break-inside: avoid;
            }}
            
            .card-header {{
                padding: 20px 25px;
                border-bottom: 1px solid var(--border-color);
                background: #fbfcbd;
                background: linear-gradient(to right, #f8fafc, #ffffff);
                border-radius: 8px 8px 0 0;
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                gap: 15px;
            }}
            
            .tender-title {{ 
                font-size: 18px; 
                font-weight: 600; 
                color: var(--text-main); 
                line-height: 1.4;
                margin-bottom: 0;
                flex: 1;
            }}
            
            .badge-container {{ flex-shrink: 0; margin-top: 2px; }}
            .badge {{ 
                padding: 6px 12px; 
                border-radius: 6px; 
                font-size: 12px; 
                font-weight: 600; 
                letter-spacing: 0.3px;
                white-space: nowrap;
            }}
            .badge-good {{ background: var(--good-fit-bg); color: var(--good-fit-text); }}
            .badge-medium {{ background: var(--medium-fit-bg); color: var(--medium-fit-text); }}
            
            .card-body {{ padding: 25px; }}
            
            /* Minimalist Data Grid */
            .data-grid {{
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 20px;
            }}
            
            .data-item {{ display: flex; flex-direction: column; gap: 4px; min-width: 0; }}
            .data-label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); font-weight: 600; }}
            .data-value {{ 
                font-size: 14px; 
                font-weight: 500; 
                color: var(--text-main); 
                word-wrap: break-word;
                overflow-wrap: break-word;
                word-break: break-word;
            }}
            
            .full-width {{ grid-column: 1 / -1; }}
            
            .deadline-highlight {{ color: #dc2626; font-weight: 600; }}
            
            a {{ color: var(--accent-blue); text-decoration: none; }}
            
            /* Footer */
            .footer {{ 
                background: #f1f5f9; 
                padding: 25px 50px; 
                display: flex;
                justify-content: space-between;
                align-items: center;
                border-top: 1px solid var(--border-color);
            }}
            .footer-logo {{ font-weight: 700; color: var(--text-main); font-size: 14px; letter-spacing: -0.3px; }}
            .footer-note {{ font-size: 12px; color: var(--text-muted); }}
            
            /* Print Specifics */
            @media print {{
                body {{ padding: 0; background-color: #fff; }}
                .report-wrapper {{ box-shadow: none; border-radius: 0; max-width: 100%; }}
                .tender-card {{ page-break-inside: avoid; }}
            }}
        </style>
    </head>
    <body>
        <div class="report-wrapper">
            <div class="header">
                <div class="header-branding">
                    <h1>Tender Intelligence Report</h1>
                    <p>Automated Opportunity Discovery & AI Classification</p>
                </div>
                <div class="header-meta">
                    <div class="date">{datetime.now().strftime('%B %d, %Y')}</div>
                    <div class="count">{len(approved_tenders) if approved_tenders else 0} Qualified Opportunities</div>
                </div>
            </div>
            
            <div class="content">
                <div class="intro-text">
                    This report contains a curated list of HVAC and Clean Room tenders strictly matched against Axenic Systems' operational capabilities. Full tender documents and HTML snapshots are securely bundled in the attached ZIP archive for immediate offline review.
                </div>
                
                <div class="tender-list">
    """
    
    if approved_tenders:
        for t in approved_tenders:
            score = t.get("confidence_score", 0)
            fit = t.get("fit_category", "Medium Fit")
            badge_class = "badge-good" if fit == "Good Fit" else "badge-medium"
            source_name = t.get("source", "Unknown")
            website_url = portal_urls.get(source_name, "Unknown URL")
            org = t.get("organisation", "Not specified")
            if not org.strip(): org = "Not specified"
            val = t.get("tender_value", "Not disclosed")
            if not val.strip(): val = "Not disclosed"
            
            html_content += f"""
                    <div class="tender-card">
                        <div class="card-header">
                            <h3 class="tender-title">{t.get('tender_title', 'Unknown Title')}</h3>
                            <div class="badge-container">
                                <span class="badge {badge_class}">{fit} · {score}%</span>
                            </div>
                        </div>
                        <div class="card-body">
                            <div class="data-grid">
                                <div class="data-item">
                                    <span class="data-label">Issuing Organisation</span>
                                    <span class="data-value">{org}</span>
                                </div>
                                <div class="data-item">
                                    <span class="data-label">Estimated Value</span>
                                    <span class="data-value">{val}</span>
                                </div>
                                <div class="data-item full-width">
                                    <span class="data-label">Source Portal</span>
                                    <span class="data-value">{source_name} &nbsp;·&nbsp; <a href="{website_url}">{website_url}</a></span>
                                </div>
                                <div class="data-item">
                                    <span class="data-label">Submission Deadline</span>
                                    <span class="data-value deadline-highlight">{t.get('closing_date', 'N/A')}</span>
                                </div>
                                <div class="data-item">
                                    <span class="data-label">Offline Snapshot</span>
                                    <span class="data-value" style="color: var(--text-muted);">✓ {os.path.basename(t.get('link', ''))}</span>
                                </div>
                            </div>
                        </div>
                    </div>
            """
            
    html_content += """
                </div>
            </div>
            
            <div class="footer">
                <div class="footer-logo">AXENIC SYSTEMS</div>
                <div class="footer-note">Confidential Document • Generated by TenderDad</div>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html_content


def generate_pdf_digest(approved_tenders: list[dict], reports_dir: str = "reports") -> str:
    """
    Generates a beautifully styled PDF report using Playwright.
    Returns the file path to the generated PDF.
    """
    os.makedirs(reports_dir, exist_ok=True)
    filename = os.path.join(reports_dir, f"tender_digest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
    
    html = generate_html_report(approved_tenders)
    
    print("[Reporter] Rendering HTML to PDF using Playwright...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html)
        
        # Add some margin for the PDF specifically
        page.pdf(
            path=filename, 
            format="A4", 
            print_background=True,
            margin={"top": "20px", "bottom": "20px"}
        )
        browser.close()
        
    return filename


def _bundle_snapshots(approved_tenders: list[dict], reports_dir: str = "reports") -> str | None:
    """
    Bundle all local HTML snapshot files referenced by approved tenders into a ZIP.
    Returns the path to the ZIP file, or None if no snapshots exist.
    """
    snapshot_paths = []
    for t in approved_tenders:
        link = t.get("link", "")
        if link and os.path.isfile(link):
            snapshot_paths.append(link)
    
    if not snapshot_paths:
        return None
    
    os.makedirs(reports_dir, exist_ok=True)
    zip_path = os.path.join(reports_dir, f"tender_snapshots_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip")
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for path in snapshot_paths:
            zf.write(path, os.path.basename(path))
    
    print(f"[Reporter] Bundled {len(snapshot_paths)} snapshots into {zip_path}")
    return zip_path


def send_email_digest(pdf_path: str, approved_tenders: list[dict] = None):
    """
    Sends the generated PDF and ZIP as email attachments.
    The email body itself is kept extremely short and professional.
    """
    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        print("[Reporter] EMAIL_SENDER or EMAIL_PASSWORD not set in .env. Skipping email.")
        return

    print(f"[Reporter] Sending email to {EMAIL_RECIPIENT}...")
    
    msg = EmailMessage()
    msg['Subject'] = f"TenderDad Digest: {len(approved_tenders) if approved_tenders else 0} New Tenders ({datetime.now().strftime('%B %d, %Y')})"
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECIPIENT
    
    # Short, professional email body
    msg.set_content(
        "Hello,\n\n"
        f"Your TenderDad daily digest is ready. We found {len(approved_tenders) if approved_tenders else 0} new approved tenders today.\n\n"
        "Attached you will find:\n"
        "1. A beautifully formatted PDF digest summarizing all the tenders.\n"
        "2. A ZIP file containing the full HTML snapshots of every tender's detail page. "
        "You can extract these and open them directly in your web browser without needing to visit the portal or solve CAPTCHAs.\n\n"
        "Best regards,\n"
        "TenderDad Auto-Scraper"
    )
    
    # Attach the beautiful digest PDF
    with open(pdf_path, 'rb') as f:
        pdf_data = f.read()
        
    msg.add_attachment(
        pdf_data, 
        maintype='application', 
        subtype='pdf', 
        filename=os.path.basename(pdf_path)
    )
    
    # Bundle and attach snapshot PDFs as ZIP
    if approved_tenders:
        zip_path = _bundle_snapshots(approved_tenders)
        if zip_path:
            with open(zip_path, 'rb') as f:
                zip_data = f.read()
            msg.add_attachment(
                zip_data,
                maintype='application',
                subtype='zip',
                filename=os.path.basename(zip_path)
            )
    
    try:
        # Connect to Gmail SMTP server
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
            smtp.send_message(msg)
        print("[Reporter] Email sent successfully!")
    except Exception as e:
        print(f"[Reporter] Failed to send email: {e}")
