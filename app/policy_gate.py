from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict
import re


@dataclass
class PolicyDecision:
    topic: str
    allow_generation: bool

    risk_tier: str = "LOW"          # LOW | MEDIUM | CRITICAL
    reason: str = ""
    matched_terms: List[str] = field(default_factory=list)
    confidence: str = "low"
    mode: str = "grounded"          # grounded | advice


def decision_to_dict(d: PolicyDecision) -> Dict:
    return {
        "risk_tier": d.risk_tier,
        "topic": d.topic,
        "allow_generation": d.allow_generation,
        "reason": d.reason,
        "matched_terms": d.matched_terms,
        "confidence": d.confidence,
        "mode": d.mode,
    }


_STOPWORDS = {
    "a","an","the","and","or","to","of","in","on","for","with","before","after","during",
    "what","is","are","was","were","be","being","been","do","does","did","how","when",
    "required","requirements","controls","steps","procedure","process","like","please",
    "must","should","can","could","would","your","our","their","it","this","that"
}


def _norm(s: str) -> str:
    return (s or "").lower()


def _chunk_texts(chunks: List[Dict]) -> str:
    return " ".join([(c.get("CHUNK_TEXT") or "") for c in (chunks or [])]).lower()


def _tokenize(text: str) -> List[str]:
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
    q = _norm(question)
    specific: List[str] = []

    if re.search(r"\bhf\b", q):
        specific.append("hf")
    if "hydrofluoric" in q:
        specific.append("hydrofluoric")
    if "acid" in q:
        specific.append("acid")
    if "digestion" in q:
        specific.append("digestion")
    if "calibrate" in q or "calibration" in q:
        specific.append("calibration")

    model_like = re.findall(r"\b[A-Z]{1,4}[-]?\d{2,6}\b", question)
    for m in model_like:
        specific.append(m.lower())

    return _unique(specific)


def _topic_from_question(question: str) -> str:
    q = _norm(question)
    if any(k in q for k in ["confined space", "entry permit", "standby", "entrant"]):
        return "confined_space"
    if any(k in q for k in ["hot work", "welding", "cutting", "grinding", "spark", "fire watch"]):
        return "hot_work"
    if any(k in q for k in ["working at heights", "fall arrest", "harness", "lanyard", "scaffold", "ewp"]):
        return "working_at_heights"
    if any(k in q for k in ["isolation", "loto", "lockout", "tagout", "prove dead", "prove-dead", "maintenance"]):
        return "isolation_loto"
    if any(k in q for k in ["ppe", "personal protective", "hard hat", "safety glasses", "gloves", "boots", "respirator"]):
        return "ppe"
    return "general"


TOPIC_EVIDENCE_TERMS: Dict[str, List[str]] = {
    "confined_space": ["confined space", "permit", "entry permit", "standby", "rescue", "entrant", "supervisor"],
    "hot_work": ["hot work", "permit", "welding", "cutting", "grinding", "spark", "fire watch", "extinguisher"],
    "working_at_heights": ["working at heights", "harness", "lanyard", "anchor", "fall arrest", "scaffold", "ewp", "guardrail"],
    "isolation_loto": ["loto", "lockout", "tagout", "isolate", "isolation", "prove dead", "try start", "group lock"],
    "ppe": ["ppe", "hard hat", "safety glasses", "gloves", "boots", "respirator", "hearing protection", "steel-capped"],
}
def _infer_topic_from_chunks(all_text: str) -> str:
    """
    If question was too generic, infer the topic from evidence terms present in retrieved chunks.
    Returns best topic by number of evidence hits; otherwise 'general'.
    """
    best_topic = "general"
    best_hits = 0

    for topic, terms in TOPIC_EVIDENCE_TERMS.items():
        hits = _has_any(all_text, terms)
        if len(hits) > best_hits:
            best_hits = len(hits)
            best_topic = topic

    return best_topic

def _doc_risk_tier(chunks: List[Dict]) -> str:
    tier_order = {"LOW": 0, "MEDIUM": 1, "CRITICAL": 2}
    best = "LOW"
    for c in chunks or []:
        t = (c.get("DOC_RISK_TIER") or "LOW").upper()
        if t not in tier_order:
            t = "LOW"
        if tier_order[t] > tier_order[best]:
            best = t
    return best


def enforce_policy(question: str, chunks: List[Dict], topic_override: str | None = None) -> PolicyDecision:
    topic = topic_override or _topic_from_question(question) or "general"

    if not chunks:
        return PolicyDecision(
            topic=topic,
            allow_generation=False,
            risk_tier="LOW",
            mode="grounded",
            reason="[NO_SOURCES] No approved sources were retrieved.",
            matched_terms=[],
            confidence="high",
        )

    all_text = _chunk_texts(chunks)
    specific_terms = _extract_specific_terms(question)
    risk_tier = _doc_risk_tier(chunks)

    # ----------------------------
    # STRICT PATH (topic != general)
    # ----------------------------
    if topic != "general":
        evidence_terms = TOPIC_EVIDENCE_TERMS.get(topic, [])
        hits = _has_any(all_text, evidence_terms)

        if not hits:
            if risk_tier == "CRITICAL":
                return PolicyDecision(
                    topic=topic,
                    allow_generation=False,
                    risk_tier=risk_tier,
                    mode="grounded",
                    reason=f"[{risk_tier}] Refused: topic '{topic}' but no evidence terms found in sources.",
                    matched_terms=[],
                    confidence="high",
                )
            return PolicyDecision(
                topic=topic,
                allow_generation=True,
                risk_tier=risk_tier,
                mode="advice",
                reason=f"[{risk_tier}] Not explicitly covered in SOP chunks for topic '{topic}'; providing general guidance only.",
                matched_terms=[],
                confidence="medium",
            )

        if specific_terms:
            spec_hits = _has_any(all_text, specific_terms)
            strong_specific = [t for t in spec_hits if t not in ("acid", "calibration")]
            if not strong_specific:
                if risk_tier == "CRITICAL":
                    return PolicyDecision(
                        topic=topic,
                        allow_generation=False,
                        risk_tier=risk_tier,
                        mode="grounded",
                        reason=f"[{risk_tier}] Refused: specific terms {specific_terms} not mentioned in sources.",
                        matched_terms=_unique(hits),
                        confidence="high",
                    )
                return PolicyDecision(
                    topic=topic,
                    allow_generation=True,
                    risk_tier=risk_tier,
                    mode="advice",
                    reason=f"[{risk_tier}] SOP chunks don't mention specific terms {specific_terms}; providing general guidance only.",
                    matched_terms=_unique(hits),
                    confidence="medium",
                )

        return PolicyDecision(
            topic=topic,
            allow_generation=True,
            risk_tier=risk_tier,
            mode="grounded",
            reason=f"[{risk_tier}] Passed: evidence terms found in sources: {hits}",
            matched_terms=_unique(hits),
            confidence="high" if len(hits) >= 3 else "medium",
        )

    # ----------------------------
    # GENERAL PATH
    # ----------------------------
    q_tokens = _unique(_tokenize(question))
    c_tokens = set(_tokenize(all_text))
    overlap = [t for t in q_tokens if t in c_tokens]

    if specific_terms:
        spec_hits = _has_any(all_text, specific_terms)
        strong_specific = [t for t in spec_hits if t not in ("acid", "calibration")]
        if not strong_specific:
            if risk_tier == "CRITICAL":
                return PolicyDecision(
                    topic="general",
                    allow_generation=False,
                    risk_tier=risk_tier,
                    mode="grounded",
                    reason=f"[{risk_tier}] Refused: specific terms {specific_terms} not found in sources.",
                    matched_terms=overlap,
                    confidence="high",
                )
            return PolicyDecision(
                topic="general",
                allow_generation=True,
                risk_tier=risk_tier,
                mode="advice",
                reason=f"[{risk_tier}] Specific terms {specific_terms} not found in sources; providing general guidance only.",
                matched_terms=overlap,
                confidence="medium",
            )

    if risk_tier == "LOW":
        min_overlap = 1
    elif risk_tier == "MEDIUM":
        min_overlap = 2
    else:  # CRITICAL
        min_overlap = 3

    if len(overlap) < min_overlap:
        # ---- Rescue: question is generic, but sources may clearly match a strict topic ----
        inferred = _infer_topic_from_chunks(all_text)

        if inferred != "general":
            evidence_terms = TOPIC_EVIDENCE_TERMS.get(inferred, [])
            hits = _has_any(all_text, evidence_terms)

            if hits:
                return PolicyDecision(
                    topic=inferred,
                    allow_generation=True,
                    risk_tier=risk_tier,
                    mode="grounded",
                    reason=f"[{risk_tier}] Passed (rescued): question was generic but sources match topic '{inferred}': {hits}",
                    matched_terms=_unique(hits),
                    confidence="high" if len(hits) >= 3 else "medium",
                )

        # ---- Original behaviour continues ----
        if risk_tier == "CRITICAL":
            return PolicyDecision(
                topic="general",
                allow_generation=False,
                risk_tier=risk_tier,
                mode="grounded",
                reason=f"[{risk_tier}] Refused: insufficient overlap between question and retrieved sources.",
                matched_terms=overlap,
                confidence="high",
            )

        return PolicyDecision(
            topic="general",
            allow_generation=True,
            risk_tier=risk_tier,
            mode="advice",
            reason=f"[{risk_tier}] Weak SOP match; providing general guidance only.",
            matched_terms=overlap,
            confidence="low" if risk_tier == "LOW" else "medium",
        )

    return PolicyDecision(
        topic="general",
        allow_generation=True,
        risk_tier=risk_tier,
        mode="grounded",
        reason=f"[{risk_tier}] Passed: overlap terms found in sources: {overlap}",
        matched_terms=overlap,
        confidence="medium",
    )