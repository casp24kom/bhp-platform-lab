# app/refusal.py
import re
from typing import Any, Dict, List, Optional, Tuple

# -----------------------------
# Smalltalk / out-of-scope
# -----------------------------
_SMALLTALK_PATTERNS = [
    r"^\s*hi\b", r"^\s*hello\b", r"^\s*hey\b",
    r"\bhow are you\b",
    r"\bwhat('?s| is) your name\b",
    r"\bwho are you\b",
    r"\bwhat can you do\b",
]

def is_smalltalk(q: str) -> bool:
    t = (q or "").strip().lower()
    return any(re.search(p, t) for p in _SMALLTALK_PATTERNS)


# -----------------------------
# Prompt injection / exfil attempts
# (hard refusal — do not retrieve, do not call model)
# -----------------------------
_INJECTION_PATTERNS = [
    r"\bignore (all|any) (previous|prior|above) instructions\b",
    r"\breveal\b.*\b(system prompt|prompt|developer message|hidden instructions)\b",
    r"\b(system prompt|developer message|hidden instructions)\b",
    r"\bpassword\b|\bapi key\b|\bsecret\b|\btoken\b",
    r"\bexfiltrat(e|ion)\b|\bleak\b|\bshow me\b.*\bsecrets\b",
    r"\bfor admin use\b|\badmin only\b|\binternal only\b",
    r"\bcall this external url\b|\bhttp(s)?://\S+\b",
    r"\brun this command\b|\bexecute\b.*\b(shell|bash|powershell)\b",
]

def is_prompt_injection(q: str) -> bool:
    t = (q or "").strip().lower()
    return any(re.search(p, t) for p in _INJECTION_PATTERNS)


# -----------------------------
# Refusal helpers
# -----------------------------
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


def _format_help_into_answer(
    headline: str,
    followups: List[str],
    rephrases: List[str],
    include_rephrases: bool = True,
) -> str:
    lines: List[str] = [headline.strip(), ""]
    if followups:
        lines.append("To help me retrieve the right SOP excerpts, please tell me:")
        for q in followups[:3]:
            lines.append(f"- {q}")
        lines.append("")
    if include_rephrases and rephrases:
        lines.append("Try asking:")
        for s in rephrases[:3]:
            lines.append(f"- {s}")
        lines.append("")
    lines.append("I won’t guess or invent details.")
    return "\n".join(lines).strip()


def _topic_for_refusal(topic: str, reason: str) -> Tuple[str, Optional[str]]:
    """
    Keep the UI clean: if the topic was only weakly inferred (rescued-weak / no relevant),
    present as 'general' but optionally include suggested_topic for UI.
    """
    t = (topic or "general").strip() or "general"
    r = (reason or "").lower()

    # If weak inference / irrelevant retrieval, don't confidently label it as a strict topic.
    if "rescued-weak" in r or "no_relevant" in r or "top retrieval score too low" in r:
        if t != "general":
            return "general", t
        return "general", None

    return t, None


def build_helpful_refusal(
    question: str,
    topic: str,
    risk_tier: str,
    reason: str,
    chunks: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Structured refusal response for:
      - smalltalk / non-SOP questions
      - prompt injection / exfil attempts
      - empty retrieval
      - weak/off-topic retrieval (policy refuses)

    Returns dict with:
      - answer: human-friendly refusal (includes follow-ups)
      - refusal: structured details for UI
      - citations: the chunks (if any)
    """
    question = question or ""
    topic = (topic or "general").strip() or "general"
    risk_tier = (risk_tier or "LOW").upper()
    reason = (reason or "").strip() or "[REFUSED]"
    citations = chunks or []

    # ---- Prompt injection hard refusal
    if is_prompt_injection(question):
        display_topic, suggested_topic = _topic_for_refusal(topic="general", reason=reason)
        followups = [
            "What SOP task are you doing (e.g., LOTO, confined space, hot work, working at heights, PPE)?",
            "What equipment/asset is involved and what step are you at (before / during / restart)?",
        ]
        rephrases = _suggest_rephrases(question, "general")

        answer = (
            "I can’t help with requests to ignore rules, reveal hidden instructions, or disclose secrets.\n"
            "If you have an SOP-related question, I can help *only* by citing approved SOP excerpts.\n\n"
            + _format_help_into_answer("", followups, rephrases).lstrip()
        ).strip()

        refusal_obj: Dict[str, Any] = {
            "type": "prompt_injection",
            "risk_tier": risk_tier,
            "topic": display_topic,
            "reason": "Out of scope / security: prompt injection or secret-exfiltration attempt.",
            "what_i_need": followups,
            "try_asking": rephrases,
            "notes": [
                "I only respond using retrieved SOP excerpts (approved sources).",
                "Rephrase as an operational SOP question to improve retrieval.",
            ],
        }
        if suggested_topic:
            refusal_obj["suggested_topic"] = suggested_topic

        return {"answer": answer, "refusal": refusal_obj, "citations": []}

    # ---- Smalltalk/out-of-scope
    if is_smalltalk(question):
        display_topic, suggested_topic = _topic_for_refusal(topic="general", reason=reason)
        followups = [
            "Which SOP topic do you want (LOTO, confined space, hot work, working at heights, PPE)?",
            "What task are you about to perform, and on what asset/equipment?",
        ]
        rephrases = _suggest_rephrases(question, "general")

        answer = (
            "Hi! 👋 I’m an SOP Q&A assistant.\n"
            "I can only answer when I can cite relevant SOP snippets from the approved sources.\n\n"
            + _format_help_into_answer("", followups, rephrases).lstrip()
        ).strip()

        refusal_obj: Dict[str, Any] = {
            "type": "smalltalk",
            "risk_tier": "LOW",
            "topic": display_topic,
            "reason": "Out of scope: smalltalk / chit-chat (not an SOP question).",
            "what_i_need": followups,
            "try_asking": rephrases,
            "notes": [
                "I only respond using retrieved SOP excerpts (approved sources).",
                "If you provide more specific task context, retrieval will improve.",
            ],
        }
        if suggested_topic:
            refusal_obj["suggested_topic"] = suggested_topic

        return {"answer": answer, "refusal": refusal_obj, "citations": []}

    # ---- Retrieval/policy refusal (empty or weak)
    display_topic, suggested_topic = _topic_for_refusal(topic=topic, reason=reason)
    followups = _follow_up_questions(display_topic if display_topic != "general" else topic)
    rephrases = _suggest_rephrases(question, display_topic if display_topic != "general" else topic)

    headline = "I can’t confirm an answer from the approved SOP sources for that question."
    answer = _format_help_into_answer(headline, followups, rephrases)

    refusal_obj = {
        "type": "no_supported_answer",
        "risk_tier": risk_tier,
        "topic": display_topic,
        "reason": reason,
        "what_i_need": followups,
        "try_asking": rephrases,
        "notes": [
            "I only respond using retrieved SOP excerpts (approved sources).",
            "If you provide more specific task context, retrieval will improve.",
        ],
    }
    if suggested_topic:
        refusal_obj["suggested_topic"] = suggested_topic

    return {
        "answer": answer,
        "refusal": refusal_obj,
        "citations": citations,
    }