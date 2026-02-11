# app/policy_gate.py
from __future__ import annotations
from typing import Any, Dict, List, Tuple

# --- helpers ---
def _norm(s: str) -> str:
    return (s or "").lower()

def _contains_any(text: str, terms: List[str]) -> List[str]:
    t = _norm(text)
    return [term for term in terms if term in t]

def _chunk_corpus(chunks: List[Dict[str, Any]]) -> str:
    return " ".join(_norm(c.get("CHUNK_TEXT", "")) for c in (chunks or []))

# --- Topic rules tuned to YOUR SOP corpus ---
# Each rule has:
# - "question_terms": terms that indicate user intent
# - "evidence_terms": terms that must appear in RETRIEVED sources to allow generation
# - optional "min_matches": require >= N evidence terms to pass (default 1)
TOPIC_RULES: Dict[str, Dict[str, Any]] = {
    # Safety fundamentals
    "ppe": {
        "question_terms": ["ppe", "personal protective", "what ppe", "required ppe", "wear", "gloves", "hard hat", "helmet", "safety glasses", "respirator", "hearing protection", "hi-vis", "boots"],
        "evidence_terms": ["ppe", "personal protective", "hard hat", "helmet", "safety glasses", "gloves", "hi-vis", "steel-capped", "boots", "hearing protection", "respiratory", "respirator", "fit-tested"],
        "min_matches": 1,
    },
    "isolation_loto": {
        "question_terms": ["isolation", "loto", "lockout", "tagout", "zero energy", "prove dead", "try start", "stored energy", "re-energisation", "energisation"],
        "evidence_terms": ["loto", "lockout", "tagout", "isolate", "isolation", "zero energy", "prove dead", "try-start", "group lock", "lock box", "stored energy", "re-energisation"],
        "min_matches": 1,
    },
    "permit_to_work": {
        "question_terms": ["permit", "permit to work", "ptw", "handover", "handback", "simops", "risk assessment", "jha", "jsa"],
        "evidence_terms": ["permit", "permit type", "handback", "close-out", "simops", "jha", "jsa", "risk assessment", "isolation points"],
        "min_matches": 1,
    },
    "confined_space": {
        "question_terms": ["confined space", "entry permit", "entrant", "standby", "rescue plan", "gas test", "atmosphere"],
        "evidence_terms": ["confined space", "permit", "standby", "rescue", "atmosphere", "oxygen", "flammables", "toxics", "ventilate", "intrinsically safe"],
        "min_matches": 1,
    },
    "hot_work": {
        "question_terms": ["hot work", "welding", "cutting", "grinding", "spark", "fire watch"],
        "evidence_terms": ["hot work", "permit", "fire watch", "combustibles", "fire blankets", "extinguishers", "spark", "welding", "cutting", "grinding", "flashback arrestors"],
        "min_matches": 1,
    },
    "working_at_heights": {
        "question_terms": ["working at heights", "work at heights", "fall arrest", "harness", "lanyard", "anchor", "scaffold", "ewp", "ladder", "tie-off", "drop zone"],
        "evidence_terms": ["working at heights", "fall", "harness", "lanyard", "anchor", "scaffold", "ewp", "ladder", "tie-off", "drop zone", "tool lanyards", "toe boards", "rescue"],
        "min_matches": 1,
    },
    "electrical_isolation": {
        "question_terms": ["electrical isolation", "arc flash", "ups", "generator", "test-before-touch", "prove dead", "energised testing", "switching"],
        "evidence_terms": ["electrical", "ups", "generators", "test-before-touch", "prove dead", "arc flash", "energised testing", "switching program", "portable earths", "substations"],
        "min_matches": 1,
    },
    "hv_switching": {
        "question_terms": ["high voltage", "hv", "switching", "switchroom", "substation", "earthing", "switching log"],
        "evidence_terms": ["switching program", "authorised", "earthing", "portable earths", "switching log", "interlocks", "substations", "exclusion zones"],
        "min_matches": 1,
    },

    # Operational risk domains
    "mobile_plant": {
        "question_terms": ["mobile plant", "haul route", "light vehicle", "heavy equipment", "spotter", "reversing", "blind side", "exclusion zone", "call-up", "radio"],
        "evidence_terms": ["separation", "designated routes", "exclusion zones", "positive communication", "radio", "blind-side", "spotters", "reversing", "pre-start checks"],
        "min_matches": 1,
    },
    "haulage_dispatch": {
        "question_terms": ["haulage", "dispatch", "speed limits", "call-ups", "tipping", "dump", "loading unit", "seat belts"],
        "evidence_terms": ["speed limits", "call-ups", "seat belts", "right-of-way", "berm", "tipping", "dump area", "safe separation"],
        "min_matches": 1,
    },
    "crushing_screening": {
        "question_terms": ["crushing", "screening", "crusher", "e-stops", "blockages", "interlocks", "belt slip", "transfer points"],
        "evidence_terms": ["walk-around", "e-stops", "start-up sequence", "blockages", "stop, isolate", "dust", "interlocks", "guards"],
        "min_matches": 1,
    },
    "conveyors": {
        "question_terms": ["conveyor", "belt", "tracking", "nip point", "pinch point", "guard", "start-up warnings", "sirens", "lights"],
        "evidence_terms": ["conveyor", "barricaded", "sirens", "lights", "nip points", "pinch points", "guards", "pre-start", "controlled restart"],
        "min_matches": 1,
    },
    "belt_splicing": {
        "question_terms": ["belt splicing", "vulcanising", "take-up", "snap-back", "tension release"],
        "evidence_terms": ["belt splicing", "stored energy", "loto", "exclusion zones", "snap-back", "tension", "controlled restart"],
        "min_matches": 1,
    },
    "pumps": {
        "question_terms": ["pump", "vibration", "seal", "cavitation", "prime", "coupling alignment"],
        "evidence_terms": ["vibration", "seal", "leaks", "overheating", "isolate", "depressurise", "prime", "cavitation", "alignment"],
        "min_matches": 1,
    },
    "pressure_systems": {
        "question_terms": ["pressure", "hydrotest", "pressure testing", "pressurise", "gauge", "fitting"],
        "evidence_terms": ["pressure rating", "exclusion zones", "pressurise gradually", "depressurise", "calibrated instruments", "projectile"],
        "min_matches": 1,
    },
    "lifting_rigging": {
        "question_terms": ["lifting", "rigging", "crane", "hoist", "sling", "swl", "critical lift", "tag line"],
        "evidence_terms": ["swl", "inspection tags", "lift plan", "exclusion zones", "suspended loads", "tag lines", "limit switches", "quarantine"],
        "min_matches": 1,
    },
    "reagents_chemicals": {
        "question_terms": ["reagent", "chemical", "sds", "eyewash", "shower", "diluting", "bund", "oxidisers", "acids", "caustics"],
        "evidence_terms": ["sds", "ppe", "bund", "segregation", "eyewash", "showers", "label", "diluting", "spill", "absorbents"],
        "min_matches": 1,
    },
    "spills_environment": {
        "question_terms": ["spill", "spill response", "contain", "booms", "bunding", "sds", "waterways"],
        "evidence_terms": ["stop the source", "exclusion zone", "contain", "spill kits", "booms", "bunding", "sds", "disposal", "report"],
        "min_matches": 1,
    },
    "fire_response": {
        "question_terms": ["fire", "extinguisher", "suppression", "muster", "emergency response plan", "engine bay", "hot work restrictions"],
        "evidence_terms": ["alarm", "emergency response plan", "extinguishers", "suppression", "evacuate", "muster", "hot work restrictions", "drills"],
        "min_matches": 1,
    },
    "emergency_response": {
        "question_terms": ["emergency", "evacuation", "muster", "signals", "controller", "drill"],
        "evidence_terms": ["muster", "evacuation routes", "signals", "controller", "roll calls", "do not re-enter", "drills"],
        "min_matches": 1,
    },
    "first_aid_reporting": {
        "question_terms": ["first aid", "incident", "near miss", "report", "notifiable", "preserve the scene"],
        "evidence_terms": ["first aid", "call for help", "report", "near misses", "preserve the scene", "notifiable", "corrective actions"],
        "min_matches": 1,
    },
    "fatigue": {
        "question_terms": ["fatigue", "fit for work", "microsleep", "breaks", "hydration", "controlled rest"],
        "evidence_terms": ["fit for work", "fatigued", "break requirements", "hydrate", "controlled rest", "microsleeps", "buddy checks"],
        "min_matches": 1,
    },
    "dust_respirable": {
        "question_terms": ["dust", "silica", "respirable", "respirator", "fit-tested", "suppression", "fog cannons", "housekeeping"],
        "evidence_terms": ["wet methods", "local extraction", "enclosure", "fit-tested", "respiratory", "filters", "housekeeping", "suppression"],
        "min_matches": 1,
    },
    "noise_hearing": {
        "question_terms": ["noise", "hearing", "hearing protection", "conservation", "high-noise"],
        "evidence_terms": ["high-noise", "hearing protection", "engineering controls", "task rotation", "hearing tests"],
        "min_matches": 1,
    },

    # Operations / governance
    "process_alarms": {
        "question_terms": ["alarm", "trip", "interlock", "override", "alarm flooding", "acknowledge"],
        "evidence_terms": ["acknowledge", "priority", "instrument validity", "high-high", "safe state", "overrides require", "logs"],
        "min_matches": 1,
    },
    "sampling_custody": {
        "question_terms": ["sampling", "chain of custody", "label", "qa/qc", "duplicates", "blanks", "standards"],
        "evidence_terms": ["representative", "label", "chain-of-custody", "qa/qc", "duplicates", "blanks", "standards", "secure locations"],
        "min_matches": 1,
    },
    "maintenance_cmms": {
        "question_terms": ["cmms", "work order", "job plan", "shutdown", "criticality", "predictive", "condition monitoring"],
        "evidence_terms": ["cmms", "work orders", "job plans", "criticality", "shutdown windows", "condition monitoring", "root cause"],
        "min_matches": 1,
    },
    "ot_cyber": {
        "question_terms": ["ot", "cyber", "usb", "mfa", "plc", "hmi", "change control", "vault", "secrets"],
        "evidence_terms": ["least privilege", "unknown usb", "media scanning", "change control", "backups", "mfa", "vault", "rotate credentials"],
        "min_matches": 1,
    },
    "contractors": {
        "question_terms": ["contractor", "induction", "licence", "competency", "pre-start meeting", "stop-work authority"],
        "evidence_terms": ["site induction", "competencies", "licences", "pre-start meeting", "stop-work authority", "monitor work quality"],
        "min_matches": 1,
    },
    "critical_controls_verification": {
        "question_terms": ["critical controls", "ccv", "verification", "barriers", "checklist", "evidence"],
        "evidence_terms": ["critical controls", "verify", "checklist", "effectiveness", "stop work", "document evidence", "re-verification"],
        "min_matches": 1,
    },
    "management_of_change": {
        "question_terms": ["change management", "moc", "rollback", "approval", "stakeholders", "post-implementation review"],
        "evidence_terms": ["formal change assessment", "approval", "rollback plan", "success criteria", "update documentation", "post-implementation review"],
        "min_matches": 1,
    },
    "wet_weather": {
        "question_terms": ["wet weather", "storm", "rain", "flooding", "traction", "visibility"],
        "evidence_terms": ["weather forecasts", "wet weather plans", "secure loose materials", "drainage", "reduce speeds", "apply exclusion zones"],
        "min_matches": 1,
    },

    # Site interfaces
    "rail_corridor": {
        "question_terms": ["rail", "track", "level crossing", "possession", "safe working authority", "overhead services"],
        "evidence_terms": ["authorisation", "track possession", "safe working authority", "designated crossing", "spotters", "clearance", "fouling the track"],
        "min_matches": 1,
    },
    "port_operations": {
        "question_terms": ["port", "wharf", "ship loader", "vessel", "marine control", "wind limits"],
        "evidence_terms": ["permits", "exclusion zones", "wind limits", "interlocks", "marine control", "housekeeping", "fall protection", "blockages stop and isolate"],
        "min_matches": 1,
    },
    "tailings_water": {
        "question_terms": ["tailings", "embankment", "freeboard", "pond", "decant", "stormwater", "pore pressure"],
        "evidence_terms": ["inspection schedule", "freeboard", "overtopping", "bunding", "stormwater", "instrumentation alarms", "stop-work trigger"],
        "min_matches": 1,
    },

    # Underground / geotech
    "ventilation_gas": {
        "question_terms": ["ventilation", "gas monitoring", "oxygen deficiency", "toxics", "diesel particulate", "refuge chamber"],
        "evidence_terms": ["ventilation fans", "gas monitoring", "calibrated detectors", "oxygen deficiency", "stop work", "retreat", "refuge chamber"],
        "min_matches": 1,
    },
    "ground_control": {
        "question_terms": ["ground control", "rockfall", "scaling", "shotcrete", "bolts", "mesh", "geotech", "raveling"],
        "evidence_terms": ["geotechnical", "rockfall", "barricades", "pre-entry inspections", "loose rocks", "stop-work triggers", "ground support"],
        "min_matches": 1,
    },

    # Misc
    "refuelling": {
        "question_terms": ["refuelling", "fuel transfer", "bonding", "earthing", "static", "fuel truck"],
        "evidence_terms": ["isolate ignition sources", "spill controls", "hoses", "couplings", "bonding", "earthing", "spill kits", "documentation"],
        "min_matches": 1,
    },
    "asset_walkdown": {
        "question_terms": ["walkdown", "asset integrity", "corrosion", "guarding", "abnormal noise", "checklist"],
        "evidence_terms": ["walkdowns", "leaks", "corrosion", "guarding", "checklist", "photos", "escalate critical defects", "cmms"],
        "min_matches": 1,
    },
    "haul_road_maintenance": {
        "question_terms": ["haul road maintenance", "berm standards", "potholes", "corrugations", "soft edges", "grading"],
        "evidence_terms": ["potholes", "corrugations", "soft edges", "berm", "signage", "speed reductions", "drainage"],
        "min_matches": 1,
    },
    "stockpiles_reclaimers": {
        "question_terms": ["stockpile", "reclaimer", "draw point", "engulfment", "bridging", "hang-ups", "reclaim tunnel"],
        "evidence_terms": ["unstable", "exclusion distances", "engulfment", "isolate", "lock out", "bridging", "dust exposure"],
        "min_matches": 1,
    },
    "hazard_reporting": {
        "question_terms": ["hazard reporting", "hazard", "corrective actions", "due dates", "trend recurring"],
        "evidence_terms": ["report hazards", "location", "potential consequence", "corrective actions", "owners", "verify corrective actions", "trend recurring"],
        "min_matches": 1,
    },
}

# Topics in priority order to avoid misclassification (e.g. PPE questions should hit "ppe")
TOPIC_PRIORITY: List[str] = [
    "ppe",
    "confined_space",
    "hot_work",
    "working_at_heights",
    "hv_switching",
    "electrical_isolation",
    "isolation_loto",
    "permit_to_work",
    "fire_response",
    "emergency_response",
    "first_aid_reporting",
    "dust_respirable",
    "noise_hearing",
    "mobile_plant",
    "haulage_dispatch",
    "crushing_screening",
    "conveyors",
    "belt_splicing",
    "pumps",
    "pressure_systems",
    "lifting_rigging",
    "reagents_chemicals",
    "spills_environment",
    "tailings_water",
    "rail_corridor",
    "port_operations",
    "ventilation_gas",
    "ground_control",
    "refuelling",
    "asset_walkdown",
    "haul_road_maintenance",
    "stockpiles_reclaimers",
    "hazard_reporting",
    "process_alarms",
    "sampling_custody",
    "maintenance_cmms",
    "ot_cyber",
    "contractors",
    "critical_controls_verification",
    "management_of_change",
    "wet_weather",
]

def classify_topic(question: str) -> str:
    q = _norm(question)
    for topic in TOPIC_PRIORITY:
        rules = TOPIC_RULES.get(topic, {})
        if any(term in q for term in rules.get("question_terms", [])):
            return topic
    return "general"

def policy_gate(question: str, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    topic = classify_topic(question)
    corpus = _chunk_corpus(chunks)

    # If we have no sources, we can’t allow generation for any non-general topic.
    if not chunks:
        return {
            "topic": topic,
            "allow_generation": False,
            "reason": "No sources retrieved; cannot answer from approved sources.",
            "matched_terms": [],
            "confidence": "high",
        }

    if topic == "general":
        # "general" is stricter than it sounds: require *some* operational evidence words
        # to reduce generic/hallucinated answers when retrieval is weak.
        general_evidence = ["permit", "loto", "isolate", "exclusion", "verify", "inspect", "test", "controls", "risk", "hazard"]
        matched = sorted(set(_contains_any(corpus, general_evidence)))
        allow = len(matched) >= 1
        return {
            "topic": "general",
            "allow_generation": allow,
            "reason": "General gate passed." if allow else "General gate failed: sources lacked basic operational evidence terms.",
            "matched_terms": matched,
            "confidence": "medium" if allow else "high",
        }

    rules = TOPIC_RULES[topic]
    evidence_terms: List[str] = rules.get("evidence_terms", [])
    min_matches: int = int(rules.get("min_matches", 1))
    matched = sorted(set(_contains_any(corpus, evidence_terms)))

    allow = len(matched) >= min_matches

    if allow:
        confidence = "high" if len(matched) >= max(3, min_matches) else "medium"
        reason = f"Policy gate passed: found evidence terms in sources: {matched[:10]}"
    else:
        confidence = "high"
        reason = f"Policy gate failed: no sufficient evidence terms found in sources for topic '{topic}'."

    return {
        "topic": topic,
        "allow_generation": allow,
        "reason": reason,
        "matched_terms": matched,
        "confidence": confidence,
    }