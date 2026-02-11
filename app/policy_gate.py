from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict
import re

@dataclass
class PolicyDecision:
    topic: str
    allow_generation: bool
    reason: str = ""
    matched_terms: List[str] = field(default_factory=list)
    confidence: str = "low"


def decision_to_dict(d: PolicyDecision) -> Dict:
    return {
        "topic": d.topic,
        "allow_generation": d.allow_generation,
        "reason": d.reason,
        "matched_terms": d.matched_terms,
        "confidence": d.confidence,
    }


# ----------------------------
# Helpers
# ----------------------------

_STOPWORDS = {
    "a","an","the","and","or","to","of","in","on","for","with","before","after","during",
    "what","is","are","was","were","be","being","been","do","does","did","how","when",
    "required","requirements","controls","steps","procedure","process","like","please",
    "must","should","can","could","would","your","our","their","it","this","that"
}

def _norm(s: str) -> str:
    return (s or "").lower()

def _chunk_texts(chunks: List[Dict]) -> str:
    parts = []
    for c in chunks or []:
        t = c.get("CHUNK_TEXT") or ""
        parts.append(t)
    return " ".join(parts).lower()

def _tokenize(text: str) -> List[str]:
    # keep alnum + dash
    toks = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", _norm(text))
    return [t for t in toks if t and t not in _STOPWORDS and len(t) >= 3]

def _unique(tokens: List[str]) -> List[str]:
    seen = set()
    out = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out

def _has_any(text: str, terms: List[str]) -> List[str]:
    hits = []
    t = _norm(text)
    for term in terms:
        if term in t:
            hits.append(term)
    return hits

def _extract_specific_terms(question: str) -> List[str]:
    """
    Pull out high-specificity items that SHOULD appear in sources if we claim coverage:
    - chemical/hazard names (hf, hydrofluoric)
    - model identifiers (xz-9000, ab123)
    - very specific noun phrases
    """
    q = _norm(question)

    specific = []

    # Chemicals / hazards (extend as you like)
    if "hf" in re.findall(r"\bhf\b", q):
        specific.append("hf")
    if "hydrofluoric" in q:
        specific.append("hydrofluoric")
    if "acid" in q:
        specific.append("acid")
    if "digestion" in q:
        specific.append("digestion")
    if "calibrate" in q or "calibration" in q:
        specific.append("calibration")

    # Model-like tokens: XZ-9000, AB123, etc.
    model_like = re.findall(r"\b[A-Z]{1,4}[-]?\d{2,6}\b", question)
    for m in model_like:
        specific.append(m.lower())

    return _unique(specific)

def _topic_from_question(question: str) -> str:
    q = _norm(question)

    # Topic routing by keyword
    if any(k in q for k in ["confined space", "entry permit", "standby", "entrant"]):
        return "confined_space"
    if any(k in q for k in ["hot work", "welding", "cutting", "grinding", "spark", "fire watch"]):
        return "hot_work"
    if any(k in q for k in ["working at heights", "fall arrest", "harness", "lanyard", "scaffold", "ewp"]):
        return "working_at_heights"
    if any(k in q for k in ["isolation", "loto", "lockout", "tagout", "prove dead", "prove-dead"]):
        return "isolation_loto"
    if any(k in q for k in ["ppe", "personal protective", "hard hat", "safety glasses", "gloves", "boots", "respirator"]):
        return "ppe"

    # default
    return "general"


# ----------------------------
# Topic rules
# ----------------------------

TOPIC_EVIDENCE_TERMS: Dict[str, List[str]] = {
    "confined_space": ["confined space", "permit", "entry permit", "standby", "rescue", "entrant", "supervisor"],
    "hot_work": ["hot work", "permit", "welding", "cutting", "grinding", "spark", "fire watch", "extinguisher"],
    "working_at_heights": ["working at heights", "harness", "lanyard", "anchor", "fall arrest", "scaffold", "ewp", "guardrail"],
    "isolation_loto": ["loto", "lockout", "tagout", "isolate", "isolation", "prove dead", "try start", "group lock"],
    "ppe": ["ppe", "hard hat", "safety glasses", "gloves", "boots", "respirator", "hearing protection", "steel-capped"],
    # general handled differently
}


def enforce_policy(question: str, chunks: List[Dict]) -> PolicyDecision:
    topic = _topic_from_question(question)

    # No sources => deny
    if not chunks:
        return PolicyDecision(
            topic=topic,
            allow_generation=False,
            reason="No approved sources were retrieved.",
            matched_terms=[],
            confidence="high",
        )

    all_text = _chunk_texts(chunks)
    specific_terms = _extract_specific_terms(question)

    # ---------
    # 1) Topic-specific evidence check
    # ---------
    if topic != "general":
        evidence_terms = TOPIC_EVIDENCE_TERMS.get(topic, [])
        hits = _has_any(all_text, evidence_terms)

        # If topic evidence isn't present, deny
        if not hits:
            return PolicyDecision(
                topic=topic,
                allow_generation=False,
                reason=f"Policy refused: topic '{topic}' but no evidence terms found in sources.",
                matched_terms=[],
                confidence="high",
            )

        # ---------
        # 2) Specificity check: if question contains specific terms, require at least one to appear in sources
        # ---------
        # Example: HF acid digestion should require "hf" or "hydrofluoric" or "digestion" in chunk text.
        # Otherwise deny (prevents generic PPE answers for specific hazards).
        if specific_terms:
            spec_hits = _has_any(all_text, specific_terms)
            # Require at least 1 specific hit beyond generic words like "acid"/"calibration"
            strong_specific = [t for t in spec_hits if t not in ("acid", "calibration")]
            if not strong_specific:
                return PolicyDecision(
                    topic=topic,
                    allow_generation=False,
                    reason=f"Policy refused: question contains specific terms {specific_terms} but sources do not mention them.",
                    matched_terms=hits,
                    confidence="high",
                )

        return PolicyDecision(
            topic=topic,
            allow_generation=True,
            reason=f"Policy gate passed: found evidence terms in sources: {hits}",
            matched_terms=_unique(hits),
            confidence="high" if len(hits) >= 3 else "medium",
        )

    # ---------
    # 3) GENERAL topic rule: default DENY unless strong overlap
    # ---------
    q_tokens = _unique(_tokenize(question))
    c_tokens = set(_tokenize(all_text))
    overlap = [t for t in q_tokens if t in c_tokens]

    # If question has high-specificity items, require overlap with them.
    if specific_terms:
        spec_hits = _has_any(all_text, specific_terms)
        strong_specific = [t for t in spec_hits if t not in ("acid", "calibration")]
        if not strong_specific:
            return PolicyDecision(
                topic="general",
                allow_generation=False,
                reason=f"Policy refused: specific terms {specific_terms} not found in sources.",
                matched_terms=overlap,
                confidence="high",
            )

    # Require at least 2 overlapping meaningful tokens to allow general answers
    if len(overlap) < 2:
        return PolicyDecision(
            topic="general",
            allow_generation=False,
            reason="Policy refused: insufficient overlap between question and retrieved sources.",
            matched_terms=overlap,
            confidence="high",
        )

    return PolicyDecision(
        topic="general",
        allow_generation=True,
        reason=f"Policy gate passed: overlap terms found in sources: {overlap}",
        matched_terms=overlap,
        confidence="medium",
    )