from typing import TypedDict, Literal
import os
from langgraph.graph import StateGraph, START, END
from config import GOOD_FIT_THRESHOLD, MEDIUM_FIT_THRESHOLD
from database import is_duplicate, save_tender
from vector_db import query_tenders, compute_confidence


# --- State Definition ---
class TenderState(TypedDict):
    tender_title: str
    raw_tender_text: str
    link: str
    source: str
    closing_date: str
    tender_id: str
    organisation: str
    tender_value: str
    is_relevant: bool
    reasoning: str
    is_duplicate: bool
    confidence_score: float
    fit_category: str


# --- Node Functions ---

def dedup_check(state: TenderState):
    """Check if we've already processed this tender."""
    print(f"---Node: Checking for duplicates---")
    title = state['tender_title']

    if is_duplicate(title):
        print("---Duplicate found! Stopping---")
        return {"is_duplicate": True}
    else:
        print("New tender found. Proceeding to scoring.")
        return {"is_duplicate": False}


def score_tender(state: TenderState):
    """Use vector similarity to score how well the tender matches company capabilities."""
    print(f"--- Node: Scoring '{state['tender_title'][:80]}...' ---")
    
    # Query the vector DB
    query_result = query_tenders(state['tender_title'])
    confidence, fit_category = compute_confidence(query_result)
    
    # Build a reasoning string from the top match
    if query_result["documents"]:
        top_match = query_result["documents"][0][:100]
        top_sim = query_result["similarities"][0] if query_result["similarities"] else 0
        reasoning = f"[{fit_category}] Confidence: {confidence}% | Top match ({top_sim:.2f}): '{top_match}...'"
    else:
        reasoning = f"[{fit_category}] Confidence: {confidence}% | No matching documents found."
    
    is_relevant = confidence >= MEDIUM_FIT_THRESHOLD
    
    print(f"  Score: {confidence}% ({fit_category})")
    
    return {
        "is_relevant": is_relevant,
        "reasoning": reasoning,
        "confidence_score": confidence,
        "fit_category": fit_category
    }


def approve_tender(state: TenderState):
    """Mark tender as approved and save to database."""
    fit = state.get('fit_category', 'Unknown')
    score = state.get('confidence_score', 0)
    print(f"--- Node: APPROVED! [{fit} — {score}%] ---")
    print(f"  Title: {state['tender_title'][:80]}")
    print(f"  Reasoning: {state.get('reasoning', 'N/A')}")
    print(f"  Link: {state.get('link', 'N/A')}")
    print(f"  Source: {state.get('source', 'N/A')}\n")
    
    save_tender(
        state['tender_title'], "approved",
        state.get('link', ''), state.get('source', ''),
        score, fit,
        state.get('closing_date', ''), state.get('tender_id', ''),
        state.get('organisation', ''), state.get('tender_value', '')
    )
    return {}


def reject_tender(state: TenderState):
    """Mark tender as rejected and save to database."""
    score = state.get('confidence_score', 0)
    fit = state.get('fit_category', 'Duplicate')
    reason = state.get('reasoning', 'Duplicate tender detected')
    print(f"--- Node: REJECTED. [{fit} — {score}%] ---")
    print(f"  Reasoning: {reason}\n")
    
    save_tender(
        state['tender_title'], "rejected",
        state.get('link', ''), state.get('source', ''),
        score, fit,
        state.get('closing_date', ''), state.get('tender_id', ''),
        state.get('organisation', ''), state.get('tender_value', '')
    )
    return {}


# --- Router Functions ---

def route_duplicate(state: TenderState) -> Literal["score", "end"]:
    return "end" if state["is_duplicate"] else "score"


def route_tender(state: TenderState) -> Literal["approve", "reject"]:
    return "approve" if state["is_relevant"] else "reject"


# --- Build the Graph ---
workflow = StateGraph(TenderState)

# Add nodes
workflow.add_node("dedup_check", dedup_check)
workflow.add_node("score", score_tender)
workflow.add_node("approve", approve_tender)
workflow.add_node("reject", reject_tender)

# Connect the flow
workflow.add_edge(START, "dedup_check")

workflow.add_conditional_edges(
    "dedup_check",
    route_duplicate,
    {"score": "score", "end": END}
)

workflow.add_conditional_edges(
    "score",
    route_tender,
    {"approve": "approve", "reject": "reject"}
)

workflow.add_edge("approve", END)
workflow.add_edge("reject", END)

# Compile into a runnable app
app = workflow.compile()
