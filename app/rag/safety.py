SAFETY_NOTICE = (
    "Prototype clinical AI response using dummy local HIS data. "
    "Not for diagnosis, treatment, or real patient care."
)


def source_confidence(sources: list[dict]) -> str:
    if not sources:
        return "none"

    top_score = sources[0].get("score", 0.0)
    if top_score >= 0.65:
        return "high"
    if top_score >= 0.35:
        return "medium"
    return "low"


def safety_warnings(sources: list[dict]) -> list[str]:
    warnings = [SAFETY_NOTICE]
    confidence = source_confidence(sources)

    if confidence in {"none", "low"}:
        warnings.append(
            "Retrieved evidence is weak or missing. Review source chunks before relying on the answer."
        )

    return warnings


def attach_safety_metadata(result: dict) -> dict:
    sources = result.get("sources", [])
    return {
        **result,
        "confidence": source_confidence(sources),
        "safety_warnings": safety_warnings(sources),
    }

