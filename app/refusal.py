# app/refusal.py
import re
from typing import Any, Dict, List, Optional


_SMALLTALK_PATTERNS = [
    r"^\s*hi\b", r"^\s*hello\b", r"^\s*hey\b",
    r"\bhow are you\b",
    r"\bwhat('?s| is) your name\b",
    r"\bwho are you\b",
    r"\bwhat can you do\b",
]

def _is_smalltalk(q: str) -> bool:
    t = (q or "").strip().lower()
    return any(re.search(p, t) for p in _SMALLTALK_PATTERNS)

def _suggest_rephrases(question: str, topic: str) -> List[str]:
    base = [
        "Add the task and equipment: “Before maintenance on <asset>, what isolation steps are required?”",
        "Add the permit/control: “What does the SOP say about <permit/control> for <task>?”",
        "Ask for a step list: “List the SOP steps for <procedure> including verification and sign-off.”",
    ]
    if topic == "isolation_loto":
        base.insert(0, "Try: “What is the lockout/tagout (LOTO) procedure before maintenance?”")
    if topic == "confined_space":
        base.insert(0, "Try: “What are the confined space entry permit and standby/rescue requirements?”")
    if topic == "hot_work":
        base.insert(0, "Try: “What hot work permit controls and fire watch requirements apply?”")
    if topic == "working_at_heights":
        base.insert(0, "Try: “What working at heights controls (harness/anchors/scaffold/EWP) are required?”")
    if topic == "ppe":
        base.insert(0, "Try: “What PPE is required for <task> and what minimum controls apply?”")
    return base[:4]

def _follow_up_questions(topic: str) -> List[str]:
    common = [
        "Which site/area or asset is this for (if known)?",
        "What exact task are you performing (e.g., inspection, belt change, welding)?",
        "Is this before starting the work, during the work, or before re-energisation/start-up?",
    ]
    topic_specific = {
        "isolation_loto": [
            "Which energy sources apply (electrical / hydraulic / pneumatic / stored energy / gravity)?",
            "Is this single-person or group isolation (lock box) work?",
        ],
        "confined_space": [
            "Is an entry permit required and who is the standby/rescue contact?",
            "What hazards are present (gas, engulfment, poor ventilation)?",
        ],
        "hot_work": [
            "What type of hot work (welding/cutting/grinding) and where is it performed?",
            "Do you need a fire watch and for how long after completion?",
        ],
        "working_at_heights": [
            "What is the height and what access method (scaffold, EWP, ladder)?",
            "Are anchor points and fall-arrest equipment specified?",
        ],
        "ppe": [
            "What task and environment (noise, dust, chemicals) drives PPE selection?",
            "Is there a specific SOP section for PPE you expect to reference?",
        ],
    }

    out: List[str] = []
    out.extend(common)
    out.extend(topic_specific.get(topic, []))
    return out[:4]


def build_helpful_refusal(
    question: str,
    topic: str,
    risk_tier: str,
    reason: str,
    chunks: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Structured refusal response for:
      - empty retrieval
      - weak/off-topic retrieval (policy refuses)
      - smalltalk / non-SOP questions

    Returns dict with:
      - answer: polite short refusal text
      - refusal: structured details for UI (follow-ups, try_asking)
      - citations: the chunks (if any)
    """
    question = question or ""
    topic = (topic or "general").strip() or "general"
    risk_tier = (risk_tier or "LOW").upper()
    reason = (reason or "").strip() or "[REFUSED]"

    smalltalk = _is_smalltalk(question)
    citations = chunks or []

    if smalltalk:
        answer = (
            "Hi! 👋 I’m an SOP Q&A assistant.\n"
            "I can only answer when I can cite relevant SOP snippets from the approved sources.\n\n"
            "If you tell me what task you’re doing (e.g., LOTO, confined space, hot work), I’ll help using the SOP excerpts."
        )
        followups = [
            "Which SOP topic do you want (LOTO, confined space, hot work, working at heights, PPE)?",
            "What task are you about to perform, and on what asset/equipment?",
        ]
        rephrases = _suggest_rephrases(question, topic)
    else:
        answer = (
            "I can’t confirm an answer from the approved SOP sources for that question.\n"
            "I won’t guess or invent details."
        )
        followups = _follow_up_questions(topic)
        rephrases = _suggest_rephrases(question, topic)

    return {
        "answer": answer,
        "refusal": {
            "type": "no_supported_answer",
            "risk_tier": risk_tier,
            "topic": topic,
            "reason": reason,
            "what_i_need": followups,
            "try_asking": rephrases,
            "notes": [
                "I only respond using retrieved SOP excerpts (approved sources).",
                "If you provide more specific task context, retrieval will improve.",
            ],
        },
        "citations": citations,
    }