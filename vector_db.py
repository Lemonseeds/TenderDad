"""
Vector DB module for TenderDad.

Ingests the offline knowledge base (capabilities.yaml) into a local ChromaDB vector store
and an in-memory BM25 index. Provides hybrid search (semantic + keyword) with reciprocal 
rank fusion, and a confidence scoring fallback for tender classification.
"""
import os
import hashlib
import json
import yaml
import re
import chromadb
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
from config import (
    KNOWLEDGE_YAML, VECTOR_DB_PATH, EMBEDDING_MODEL,
    CHUNK_SIZE, CHUNK_OVERLAP, GOOD_FIT_THRESHOLD, MEDIUM_FIT_THRESHOLD
)

# --- Globals (initialized lazily) ---
_model = None
_collection = None
_bm25 = None
_bm25_docs = []
_bm25_metadatas = []


def _get_model():
    """Lazy-load the embedding model."""
    global _model
    if _model is None:
        print("[VectorDB] Loading embedding model...")
        # e5 models require instructions
        _model = SentenceTransformer(EMBEDDING_MODEL)
        print(f"[VectorDB] Model '{EMBEDDING_MODEL}' loaded.")
    return _model


def _get_collection():
    """Get or create the ChromaDB collection."""
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=VECTOR_DB_PATH)
        _collection = client.get_or_create_collection(
            name="company_knowledge",
            metadata={"hnsw:space": "cosine"}
        )
    return _collection


def _chunk_text_sentences(text: str, target_size: int = CHUNK_SIZE) -> list[str]:
    """Sentence-aware chunking."""
    # Split on sentence boundaries (e.g., period followed by space and capital letter)
    # or simple punctuation splits
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    
    chunks = []
    current_chunk = []
    current_length = 0
    
    for sentence in sentences:
        if not sentence.strip():
            continue
        sentence_len = len(sentence)
        if current_length + sentence_len > target_size and current_chunk:
            chunks.append(" ".join(current_chunk))
            current_chunk = [sentence]
            current_length = sentence_len
        else:
            current_chunk.append(sentence)
            current_length += sentence_len + 1 # +1 for space
            
    if current_chunk:
        chunks.append(" ".join(current_chunk))
        
    return chunks


def _compute_yaml_hash(yaml_path: str) -> str:
    """Compute a hash of the YAML file to detect changes."""
    if not os.path.exists(yaml_path):
        return ""
    hasher = hashlib.md5()
    with open(yaml_path, "rb") as f:
        hasher.update(f.read())
    return hasher.hexdigest()


def load_knowledge_base():
    """
    Load capabilities.yaml into ChromaDB (if changed) and build in-memory BM25 index.
    """
    global _bm25, _bm25_docs, _bm25_metadatas
    
    if not os.path.exists(KNOWLEDGE_YAML):
        print(f"[VectorDB] Knowledge base not found at {KNOWLEDGE_YAML}")
        return
        
    with open(KNOWLEDGE_YAML, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
        
    capabilities = data.get("capabilities", [])
    past_projects = data.get("past_projects", [])
    
    all_docs = []
    all_ids = []
    all_metadatas = []
    
    # 1. Process Capabilities (atomic, no chunking needed)
    for i, cap in enumerate(capabilities):
        doc_text = f"passage: {cap.strip()}"
        all_docs.append(doc_text)
        all_ids.append(f"capability_{i}")
        all_metadatas.append({"source_type": "capability", "index": i})
        
    # 2. Process Past Projects (chunk the description if long)
    for i, proj in enumerate(past_projects):
        client = proj.get("client", "")
        area = proj.get("area", "")
        classification = proj.get("classification", "")
        desc = proj.get("description", "")
        
        full_text = f"Project for {client}. Area: {area}. Classification: {classification}. Description: {desc}"
        chunks = _chunk_text_sentences(full_text)
        
        for chunk_idx, chunk in enumerate(chunks):
            doc_text = f"passage: {chunk}"
            all_docs.append(doc_text)
            all_ids.append(f"project_{i}_chunk_{chunk_idx}")
            all_metadatas.append({"source_type": "past_project", "index": i, "chunk": chunk_idx})
            
    if not all_docs:
        print("[VectorDB] No documents found in knowledge base!")
        return
        
    # --- Build BM25 Index (always built in-memory) ---
    print(f"[VectorDB] Building BM25 index with {len(all_docs)} documents...")
    tokenized_docs = [doc.lower().split() for doc in all_docs]
    _bm25 = BM25Okapi(tokenized_docs)
    _bm25_docs = all_docs
    _bm25_metadatas = all_metadatas
    
    # --- Populate ChromaDB (only if hash changed) ---
    collection = _get_collection()
    hash_file = os.path.join(VECTOR_DB_PATH, "kb_hash.json")
    current_hash = _compute_yaml_hash(KNOWLEDGE_YAML)
    
    if os.path.exists(hash_file):
        with open(hash_file, "r") as f:
            stored = json.load(f)
        if stored.get("hash") == current_hash and collection.count() > 0:
            print(f"[VectorDB] Vector DB already up to date ({collection.count()} docs). Skipping ingestion.")
            return

    print("[VectorDB] Ingesting into Vector DB...")
    existing = collection.get()
    if existing["ids"]:
        collection.delete(ids=existing["ids"])
        
    model = _get_model()
    
    print(f"[VectorDB] Embedding {len(all_docs)} chunks...")
    embeddings = model.encode(all_docs, show_progress_bar=True).tolist()
    
    batch_size = 500
    for i in range(0, len(all_docs), batch_size):
        end = min(i + batch_size, len(all_docs))
        collection.add(
            ids=all_ids[i:end],
            documents=all_docs[i:end],
            embeddings=embeddings[i:end],
            metadatas=all_metadatas[i:end]
        )
        
    os.makedirs(VECTOR_DB_PATH, exist_ok=True)
    with open(hash_file, "w") as f:
        json.dump({"hash": current_hash}, f)
        
    print(f"[VectorDB] Done! {len(all_docs)} docs ingested into ChromaDB.\n")


def query_tenders(tender_text: str, top_k: int = 5) -> dict:
    """
    Query the vector DB + BM25 using reciprocal rank fusion.
    """
    global _bm25, _bm25_docs, _bm25_metadatas
    
    # Ensure loaded
    if _bm25 is None:
        load_knowledge_base()
        
    if _bm25 is None:
        print("[VectorDB] Warning: Knowledge base could not be loaded!")
        return {"similarities": [], "documents": [], "metadatas": []}

    model = _get_model()
    collection = _get_collection()

    # E5 models require "query: " prefix
    formatted_query = f"query: {tender_text}"
    query_embedding = model.encode(formatted_query).tolist()

    # Get more results from vector search to fuse properly
    fetch_k = max(20, top_k * 2)
    
    # 1. Vector Search
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(fetch_k, collection.count()),
        include=["documents", "metadatas", "distances"]
    )
    
    vector_docs = results["documents"][0] if results["documents"] else []
    vector_distances = results["distances"][0] if results["distances"] else []
    vector_metas = results["metadatas"][0] if results["metadatas"] else []
    
    # Convert distances to similarities (0 to 1)
    vector_similarities = [max(0.0, 1.0 - d) for d in vector_distances]
    
    # 2. BM25 Search
    tokenized_query = tender_text.lower().split()
    bm25_scores = _bm25.get_scores(tokenized_query)
    
    # Sort all docs by BM25 score
    bm25_ranked_indices = sorted(range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True)[:fetch_k]
    
    # 3. Reciprocal Rank Fusion (RRF)
    # RRF_score = 1 / (k + rank_vector) + 1 / (k + rank_bm25)
    rrf_k = 60
    doc_rrf_scores = {}
    doc_to_meta = {}
    doc_to_sim = {}
    
    # Add vector ranks
    for rank, doc in enumerate(vector_docs):
        doc_rrf_scores[doc] = 1.0 / (rrf_k + rank + 1)
        doc_to_meta[doc] = vector_metas[rank]
        doc_to_sim[doc] = vector_similarities[rank]
        
    # Add BM25 ranks
    for rank, idx in enumerate(bm25_ranked_indices):
        doc = _bm25_docs[idx]
        score = 1.0 / (rrf_k + rank + 1)
        doc_rrf_scores[doc] = doc_rrf_scores.get(doc, 0.0) + score
        if doc not in doc_to_meta:
            doc_to_meta[doc] = _bm25_metadatas[idx]
            # Since it wasn't in vector top-k, assign a baseline similarity or 0
            doc_to_sim[doc] = 0.0 
            
    # Sort by RRF score
    sorted_docs = sorted(doc_rrf_scores.keys(), key=lambda d: doc_rrf_scores[d], reverse=True)
    top_docs = sorted_docs[:top_k]
    
    final_similarities = [doc_to_sim[d] for d in top_docs]
    final_metadatas = [doc_to_meta[d] for d in top_docs]
    
    return {
        "similarities": final_similarities,
        "documents": top_docs,
        "metadatas": final_metadatas
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
