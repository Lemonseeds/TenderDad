"""
Vector DB module for TenderDad.

Ingests company PDFs into a local ChromaDB vector store, and provides
semantic similarity search + confidence scoring for tender classification.
"""
import os
import hashlib
import json
import pymupdf  # PyMuPDF
import chromadb
from sentence_transformers import SentenceTransformer
from config import (
    PDF_FOLDER, VECTOR_DB_PATH, EMBEDDING_MODEL,
    CHUNK_SIZE, CHUNK_OVERLAP, GOOD_FIT_THRESHOLD, MEDIUM_FIT_THRESHOLD
)

# --- Globals (initialized lazily) ---
_model = None
_collection = None


def _get_model():
    """Lazy-load the embedding model."""
    global _model
    if _model is None:
        print("[VectorDB] Loading embedding model...")
        _model = SentenceTransformer(EMBEDDING_MODEL)
        print(f"[VectorDB] Model '{EMBEDDING_MODEL}' loaded.")
    return _model


def _get_collection():
    """Get or create the ChromaDB collection."""
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=VECTOR_DB_PATH)
        _collection = client.get_or_create_collection(
            name="company_docs",
            metadata={"hnsw:space": "cosine"}
        )
    return _collection


def _extract_text_from_pdf(pdf_path: str) -> str:
    """Extract all text from a PDF file using PyMuPDF."""
    doc = pymupdf.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:  # Skip empty chunks
            chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


def _compute_pdf_hash(pdf_folder: str) -> str:
    """Compute a combined hash of all PDFs in the folder to detect changes."""
    hasher = hashlib.md5()
    pdf_files = sorted([f for f in os.listdir(pdf_folder) if f.lower().endswith('.pdf')])
    for fname in pdf_files:
        fpath = os.path.join(pdf_folder, fname)
        hasher.update(fname.encode())
        hasher.update(str(os.path.getsize(fpath)).encode())
        hasher.update(str(os.path.getmtime(fpath)).encode())
    return hasher.hexdigest()


def ingest_pdfs(pdf_folder: str = PDF_FOLDER):
    """
    Ingest all PDFs from the folder into ChromaDB.
    Skips if the DB already exists and PDFs haven't changed.
    """
    collection = _get_collection()
    hash_file = os.path.join(VECTOR_DB_PATH, "pdf_hash.json")
    current_hash = _compute_pdf_hash(pdf_folder)

    # Check if we already ingested these exact PDFs
    if os.path.exists(hash_file):
        with open(hash_file, "r") as f:
            stored = json.load(f)
        if stored.get("hash") == current_hash and collection.count() > 0:
            print(f"[VectorDB] PDF database already up to date ({collection.count()} chunks). Skipping ingestion.")
            return

    # Clear existing data and re-ingest
    print("[VectorDB] Ingesting PDFs...")
    
    # Delete all existing documents
    existing = collection.get()
    if existing["ids"]:
        collection.delete(ids=existing["ids"])

    model = _get_model()

    pdf_files = [f for f in os.listdir(pdf_folder) if f.lower().endswith('.pdf')]
    if not pdf_files:
        print(f"[VectorDB] No PDF files found in '{pdf_folder}'!")
        return

    all_chunks = []
    all_ids = []
    all_metadatas = []

    for pdf_file in pdf_files:
        pdf_path = os.path.join(pdf_folder, pdf_file)
        print(f"[VectorDB] Extracting text from: {pdf_file}")
        text = _extract_text_from_pdf(pdf_path)
        
        if not text.strip():
            print(f"[VectorDB] Warning: No text extracted from {pdf_file}")
            continue
        
        chunks = _chunk_text(text)
        print(f"[VectorDB]   -> {len(chunks)} chunks from {pdf_file}")

        for i, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            all_ids.append(f"{pdf_file}_{i}")
            all_metadatas.append({"source": pdf_file, "chunk_index": i})

    # Add explicit capability keywords as high-signal anchor documents.
    # These short phrases match closely with tender titles and boost scores
    # for the company's core competencies.
    capability_anchors = [
        "HVAC system design, supply, installation, testing and commissioning",
        "Clean room construction and validation",
        "Air Handling Unit AHU supply and installation",
        "Supply and installation of AHU and ducting system",
        "Ducting fabrication and installation for HVAC systems",
        "AHU and ducting installations",
        "HVAC work for clean room and laboratory",
        "HVAC work for clean room construction",
        "Heating ventilation and air conditioning HVAC contractor",
        "Cleanroom HVAC system for pharmaceutical and hospital",
        "Central air conditioning system installation and maintenance",
        "Chiller plant room equipment supply and installation",
        "GI ducting MS ducting and insulation work",
        "HVAC AMC annual maintenance contract",
        "VRF VRV system supply and installation",
        "Precision air conditioning for data center and server room",
        "Modular clean room and pass box and air shower",
        "Exhaust system and fume hood installation",
        "BMS building management system for HVAC",
    ]
    for i, anchor in enumerate(capability_anchors):
        all_chunks.append(anchor)
        all_ids.append(f"capability_anchor_{i}")
        all_metadatas.append({"source": "company_capabilities", "chunk_index": i})
    
    print(f"[VectorDB]   -> {len(capability_anchors)} capability anchor documents added")

    if not all_chunks:
        print("[VectorDB] No text extracted from any PDF!")
        return

    # Embed all chunks
    print(f"[VectorDB] Embedding {len(all_chunks)} chunks...")
    embeddings = model.encode(all_chunks, show_progress_bar=True).tolist()

    # Add to ChromaDB (in batches of 500 to avoid limits)
    batch_size = 500
    for i in range(0, len(all_chunks), batch_size):
        end = min(i + batch_size, len(all_chunks))
        collection.add(
            ids=all_ids[i:end],
            documents=all_chunks[i:end],
            embeddings=embeddings[i:end],
            metadatas=all_metadatas[i:end]
        )

    # Save the hash so we skip next time
    os.makedirs(VECTOR_DB_PATH, exist_ok=True)
    with open(hash_file, "w") as f:
        json.dump({"hash": current_hash}, f)

    print(f"[VectorDB] Done! {len(all_chunks)} chunks ingested into ChromaDB.\n")


def query_tenders(tender_text: str, top_k: int = 5) -> dict:
    """
    Query the vector DB for the most similar company document chunks.
    
    Returns a dict with:
        - similarities: list of float (cosine similarity scores, 0-1)
        - documents: list of str (matching text chunks)
        - metadatas: list of dict (source file info)
    """
    model = _get_model()
    collection = _get_collection()

    if collection.count() == 0:
        print("[VectorDB] Warning: Vector DB is empty! Run ingest_pdfs() first.")
        return {"similarities": [], "documents": [], "metadatas": []}

    # Embed the tender text
    query_embedding = model.encode(tender_text).tolist()

    # Query ChromaDB
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"]
    )

    # ChromaDB returns cosine distances (0 = identical, 2 = opposite)
    # Convert to similarity: similarity = 1 - distance
    distances = results["distances"][0] if results["distances"] else []
    similarities = [max(0, 1 - d) for d in distances]

    return {
        "similarities": similarities,
        "documents": results["documents"][0] if results["documents"] else [],
        "metadatas": results["metadatas"][0] if results["metadatas"] else []
    }


def compute_confidence(query_result: dict) -> tuple[float, str]:
    """
    Compute the confidence score using the formula:
        confidence = 100 x (0.6 x max_similarity + 0.4 x mean_top_3_similarity)
    
    Returns:
        (confidence_score, fit_category)
        where fit_category is one of: "Good Fit", "Medium Fit", "Bad Fit"
    """
    similarities = query_result.get("similarities", [])

    if not similarities:
        return 0.0, "Bad Fit"

    max_sim = max(similarities)
    top_3 = sorted(similarities, reverse=True)[:3]
    mean_top_3 = sum(top_3) / len(top_3)

    confidence = 100 * (0.6 * max_sim + 0.4 * mean_top_3)

    if confidence >= GOOD_FIT_THRESHOLD:
        fit_category = "Good Fit"
    elif confidence >= MEDIUM_FIT_THRESHOLD:
        fit_category = "Medium Fit"
    else:
        fit_category = "Bad Fit"

    return round(confidence, 1), fit_category
