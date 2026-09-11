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
    matched_evidence: str


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


import json
from groq import Groq
from config import CLASSIFICATION_MODELS

# --- Groq Client ---
client = Groq()

def score_tender(state: TenderState):
    """Use vector similarity + LLM judgment to score how well the tender matches company capabilities."""
    print(f"--- Node: Scoring '{state['tender_title'][:80]}...' ---")
    
    # Query the vector DB (Part 2)
    query_result = query_tenders(state['tender_title'])
    
    # Pure-math fallback calculation (from Part 2)
    math_confidence, math_fit_category = compute_confidence(query_result)
    
    # If no documents are returned at all, don't even bother the LLM
    if not query_result["documents"]:
        reasoning = f"[{math_fit_category}] Auto-scored: No matching documents found."
        print(f"  Score: {math_confidence}% ({math_fit_category})")
        return {
            "is_relevant": False,
            "reasoning": reasoning,
            "confidence_score": math_confidence,
            "fit_category": math_fit_category
        }

    # Prepare retrieved documents context
    context_str = ""
    for idx, doc in enumerate(query_result["documents"]):
        sim = query_result["similarities"][idx]
        context_str += f"- [Sim: {sim:.2f}] {doc}\n"

    # Define Few-Shot Examples
    system_prompt = """You are an expert sales engineer evaluating business opportunities (tenders) for Axenic Systems.
Axenic specializes in Cleanroom Projects & Services, Modular Cleanroom Systems, HVAC (High side & Low side), BMS, and Cleanroom Equipment (Pass Boxes, Laminar Flow Units).

Your job is to determine if a tender is a Good Fit, Medium Fit, or Bad Fit based on the retrieved company capabilities and past projects.

Examples:
- Good Fit: "SITC of Modular Clean Room and HVAC System for Pharmaceutical Plant." (Aligns perfectly with core cleanroom and HVAC turnkey capabilities).
- Medium Fit: "Annual Maintenance Contract for Chiller Plants and AHUs." (Relevant to HVAC, but is maintenance rather than turnkey project).
- Bad Fit: "Construction of RCC boundary wall and civil works." (Irrelevant to cleanrooms or HVAC).

Force your output to be a valid JSON object matching this structure EXACTLY:
{
  "score": <int between 0 and 100>,
  "fit_category": "Good Fit" | "Medium Fit" | "Bad Fit",
  "reasoning": "<string explaining the decision>",
  "matched_evidence": ["<string referencing a specific capability or project>"]
}
"""

    user_prompt = f"""Tender Title: {state['tender_title']}

Retrieved Company Capabilities & Past Projects:
{context_str}

Evaluate this tender."""

    # Try LLM Judgment
    for model_name in CLASSIFICATION_MODELS:
        try:
            print(f"[Scoring] Calling LLM ({model_name})...")
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0,
                response_format={"type": "json_object"}
            )
            
            raw_text = response.choices[0].message.content.strip()
            result_json = json.loads(raw_text)
            
            score = float(result_json.get("score", 0))
            fit_category = result_json.get("fit_category", "Bad Fit")
            reasoning = result_json.get("reasoning", "")
            matched_evidence = result_json.get("matched_evidence", [])
            
            # Format evidence
            evidence_str = " | ".join(matched_evidence) if matched_evidence else "None"
            final_reasoning = f"[{fit_category}] LLM Reasoning: {reasoning} (Evidence: {evidence_str})"
            is_relevant = fit_category in ["Good Fit", "Medium Fit"]
            
            print(f"  Score: {score}% ({fit_category})")
            
            # Update state with new matched_evidence field indirectly via reasoning or if we want to store it explicitly
            # Wait, Part 3 says "Update the TenderState schema and database.py if needed to store matched_evidence".
            # I will add matched_evidence to the returned dict so state is updated.
            return {
                "is_relevant": is_relevant,
                "reasoning": final_reasoning,
                "confidence_score": score,
                "fit_category": fit_category,
                "matched_evidence": json.dumps(matched_evidence) # store as JSON string
            }
            
        except Exception as model_err:
            err_str = str(model_err).lower()
            if any(code in err_str for code in ["429", "503", "400", "404", "capacity", "rate limit", "rate_limit", "limit", "decommissioned"]):
                print(f"[Scoring] Model {model_name} failed ({err_str}). Trying next model...")
                continue
            else:
                print(f"[Scoring] Model {model_name} encountered an unexpected error: {model_err}")
                continue

    # Fallback Path (if all models fail)
    print("[Scoring] ALL LLMs FAILED OR UNAVAILABLE. Falling back to pure-math cosine similarity score.")
    reasoning = f"auto-scored, unverified — LLM unavailable. (Top match sim: {query_result['similarities'][0]:.2f})"
    is_relevant = math_confidence >= MEDIUM_FIT_THRESHOLD
    
    print(f"  Fallback Score: {math_confidence}% ({math_fit_category})")
    
    return {
        "is_relevant": is_relevant,
        "reasoning": reasoning,
        "confidence_score": math_confidence,
        "fit_category": math_fit_category,
        "matched_evidence": "[]"
    }



def approve_tender(state: TenderState):
    """Mark tender as approved and save to database."""
    fit = state.get('fit_category', 'Unknown')
    score = state.get('confidence_score', 0)
    print(f"--- Node: APPROVED! [{fit} — {score}%] ---")
    print(f"  Title: {state['tender_title'][:80]}")
    safe_reasoning = state.get('reasoning', 'N/A').encode('ascii', 'replace').decode('ascii')
    print(f"  Reasoning: {safe_reasoning}")
    print(f"  Link: {state.get('link', 'N/A')}")
    print(f"  Source: {state.get('source', 'N/A')}\n")
    
    save_tender(
        state['tender_title'], "approved",
        state.get('link', ''), state.get('source', ''),
        score, fit,
        state.get('closing_date', ''), state.get('tender_id', ''),
        state.get('organisation', ''), state.get('tender_value', ''),
        state.get('reasoning', ''), state.get('matched_evidence', '')
    )
    return {}


def reject_tender(state: TenderState):
    """Mark tender as rejected and save to database."""
    score = state.get('confidence_score', 0)
    fit = state.get('fit_category', 'Duplicate')
    reason = state.get('reasoning', 'Duplicate tender detected')
    print(f"--- Node: REJECTED. [{fit} — {score}%] ---")
    safe_reason = reason.encode('ascii', 'replace').decode('ascii')
    print(f"  Reasoning: {safe_reason}\n")
    
    save_tender(
        state['tender_title'], "rejected",
        state.get('link', ''), state.get('source', ''),
        score, fit,
        state.get('closing_date', ''), state.get('tender_id', ''),
        state.get('organisation', ''), state.get('tender_value', ''),
        reason, state.get('matched_evidence', '')
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
