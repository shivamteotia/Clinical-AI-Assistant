import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from app.rag.answering import answer_question
from app.rag.vector_store import rebuild_vector_store

EVAL_CASES = [
    {
        "query": "Which patient has diabetes and high HbA1c?",
        "expected_patient_id": "P001",
        "expected_terms": ["diabetes", "HbA1c"],
    },
    {
        "query": "Which patient has asthma symptoms?",
        "expected_patient_id": "P002",
        "expected_terms": ["asthma"],
    },
    {
        "query": "Who had chest discomfort and shortness of breath?",
        "expected_patient_id": "P003",
        "expected_terms": ["chest discomfort", "shortness of breath"],
    },
    {
        "query": "What medication is P001 taking?",
        "expected_patient_id": "P001",
        "expected_terms": ["metformin"],
    },
    {
        "query": "Which patient has chronic kidney disease with reduced eGFR?",
        "expected_patient_id": "P009",
        "expected_terms": ["chronic kidney disease", "eGFR"],
    },
    {
        "query": "Which patient has iron deficiency anemia?",
        "expected_patient_id": "P008",
        "expected_terms": ["iron deficiency anemia", "hemoglobin"],
    },
    {
        "query": "Who has burning urination and fever?",
        "expected_patient_id": "P004",
        "expected_terms": ["burning urination", "fever"],
    },
    {
        "query": "Which patient has rheumatoid arthritis and positive rheumatoid factor?",
        "expected_patient_id": "P018",
        "expected_terms": ["rheumatoid arthritis", "rheumatoid factor"],
    },
]


def main() -> None:
    rebuild = "--rebuild" in sys.argv
    if rebuild:
        rebuild_vector_store()

    passed = 0
    print("RAG Evaluation")
    print("==============")

    for index, case in enumerate(EVAL_CASES, start=1):
        result = answer_question(case["query"], k=3)
        answer = result["answer"]
        top_source = result["sources"][0] if result["sources"] else None
        top_patient_id = top_source["metadata"]["patient_id"] if top_source else None

        patient_ok = top_patient_id == case["expected_patient_id"]
        evidence_text = " ".join(
            source["page_content"] for source in result["sources"] if source["metadata"]["patient_id"] == case["expected_patient_id"]
        )
        searchable_text = f"{answer} {evidence_text}".lower()
        terms_ok = all(term.lower() in searchable_text for term in case["expected_terms"])
        case_passed = patient_ok and terms_ok
        passed += int(case_passed)

        status = "PASS" if case_passed else "FAIL"
        print(f"\n{index}. {status}: {case['query']}")
        print(f"   expected patient: {case['expected_patient_id']}")
        print(f"   top patient:      {top_patient_id}")
        print(f"   confidence:       {result['confidence']}")
        print(f"   answer:           {answer[:220]}...")

    print("\nSummary")
    print(f"Passed: {passed}/{len(EVAL_CASES)}")

    if passed != len(EVAL_CASES):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
