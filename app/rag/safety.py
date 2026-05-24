SAFETY_NOTICE = (
    "Prototype clinical AI response using dummy local HIS data. "
    "Not for diagnosis, treatment, or real patient care."
)

INTENT_PATTERNS = {
    "emergency": [
        "emergency",
        "urgent",
        "er",
        "casualty",
        "chest pain",
        "stroke",
        "suicide",
        "unconscious",
        "severe bleeding",
    ],
    "treatment_request": [
        "treat",
        "treatment",
        "therapy",
        "prescribe",
        "should take",
        "should start",
        "should stop",
        "stop medication",
        "stop medicine",
        "increase",
        "decrease",
        "dose",
        "dosage",
        "medication change",
    ],
    "diagnosis_request": [
        "diagnose",
        "diagnosis",
        "what disease",
        "does this patient have",
        "is this patient having",
    ],
    "comparison": [
        "compare",
        "versus",
        "vs",
        "which patient",
        "who has",
    ],
    "summarization": [
        "summarize",
        "summary",
        "overview",
        "record",
        "history",
    ],
}

LIMITATIONS = [
    "Uses dummy local HIS data only.",
    "Retrieval may miss relevant context if records are incomplete or phrased differently.",
    "Does not provide diagnosis, treatment, triage, or medication instructions.",
]


def classify_query_intent(query: str) -> str:
    normalized = query.lower()
    for intent, patterns in INTENT_PATTERNS.items():
        if any(pattern in normalized for pattern in patterns):
            return intent
    return "record_lookup"


def safety_level_for_intent(intent: str) -> str:
    if intent == "emergency":
        return "urgent"
    if intent in {"diagnosis_request", "treatment_request"}:
        return "restricted"
    return "standard"


def is_restricted_intent(intent: str) -> bool:
    return safety_level_for_intent(intent) in {"restricted", "urgent"}


def source_confidence(sources: list[dict]) -> str:
    if not sources:
        return "none"

    top_score = sources[0].get("score", 0.0)
    if top_score >= 0.65:
        return "high"
    if top_score >= 0.35:
        return "medium"
    return "low"


def safety_warnings(sources: list[dict], intent: str = "record_lookup") -> list[str]:
    warnings = [SAFETY_NOTICE]
    confidence = source_confidence(sources)
    safety_level = safety_level_for_intent(intent)

    if confidence in {"none", "low"}:
        warnings.append(
            "Retrieved evidence is weak or missing. Review source chunks before relying on the answer."
        )
    if safety_level == "restricted":
        warnings.append(
            "The question asks for diagnosis or treatment guidance. This prototype can only summarize retrieved record evidence."
        )
    if safety_level == "urgent":
        warnings.append(
            "The question may involve urgent symptoms. Seek emergency clinical care through appropriate local channels."
        )

    return warnings


def attach_safety_metadata(result: dict, query: str = "") -> dict:
    sources = result.get("sources", [])
    intent = result.get("intent") or classify_query_intent(query)
    safety_level = result.get("safety_level") or safety_level_for_intent(intent)
    return {
        **result,
        "intent": intent,
        "safety_level": safety_level,
        "confidence": source_confidence(sources),
        "safety_warnings": safety_warnings(sources, intent),
        "limitations": result.get("limitations", LIMITATIONS),
    }
