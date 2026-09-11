# TenderDad 🏗️

TenderDad is an automated, AI-powered intelligence pipeline designed to scrape, extract, and classify government tenders from Indian procurement portals (CPPP / GePNIC). 

It specifically targets domains like HVAC, Clean Room Construction, and critical infrastructure, using LLM-backed Vector Database scoring to evaluate if a tender matches your company's core capabilities.

## Features

- **Automated Web Scraping:** Bypasses basic session restrictions using Playwright to scrape live tender data from GePNIC/CPPP portals.
- **Offline HTML Snapshots:** Since government portal links expire rapidly, TenderDad automatically captures full HTML snapshots of approved tenders for offline review without needing to re-solve CAPTCHAs.
- **AI Match Scoring:** Uses a local Vector Database (`ChromaDB` + `SentenceTransformers`) to semantically score incoming tenders against your company's capability profile.
- **LangGraph Pipeline:** Orchestrates deduplication, LLM-based scoring, and final approval/rejection logic using a directed AI graph (`langgraph`).
- **Premium Reporting:** Automatically generates beautifully styled, enterprise-grade PDF digests using HTML-to-PDF rendering, and emails them to stakeholders along with a ZIP bundle of the HTML snapshots.

## Architecture

1. **Scraping Nodes (`scrapers/`)**: Extracts raw tender rows and detail links.
2. **Database (`database.py`)**: SQLite storage to track processed tenders and prevent duplicates.
3. **Vector DB (`vector_db.py`)**: Computes semantic similarity between tender descriptions and the company's PDFs/capabilities.
4. **Pipeline (`pipeline.py`)**: The LangGraph state machine orchestrating the flow.
5. **Reporter (`reporter.py`)**: Generates the final HTML layout, renders the PDF via Playwright, and dispatches the email.

## Setup

1. Clone the repository.
2. Create a virtual environment and install dependencies.
3. Create a `.env` file with the following variables:
   ```
   EMAIL_SENDER="your-email@gmail.com"
   EMAIL_PASSWORD="your-app-password"
   EMAIL_RECIPIENT="stakeholder@company.com"
   GROQ_API_KEY="your-groq-api-key"
   ```
4. Place your company capability PDFs in the `docs/` folder.
5. Run the pipeline: `python main.py`

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
