from langchain_core.documents import Document

from app.api.his import get_patient_record, list_patients


def _format_section(title: str, rows: list[dict]) -> str:
    if not rows:
        return f"{title}:\n- None recorded"

    lines = [f"{title}:"]
    for row in rows:
        values = [f"{key}: {value}" for key, value in row.items()]
        lines.append("- " + "; ".join(values))
    return "\n".join(lines)


def _format_patient_record(record: dict) -> str:
    patient = record["patient"]
    sections = [
        "Patient Summary:",
        f"patient_id: {patient['patient_id']}",
        f"name: {patient['name']}",
        f"age: {patient['age']}",
        f"gender: {patient['gender']}",
        f"phone: {patient['phone']}",
        f"address: {patient['address']}",
        "",
        _format_section("Encounters", record["encounters"]),
        "",
        _format_section("Lab Results", record["labs"]),
        "",
        _format_section("Medications", record["medications"]),
        "",
        _format_section("Clinical Notes", record["clinical_notes"]),
    ]
    return "\n".join(sections)


def load_patient_documents() -> list[Document]:
    documents = []
    for patient in list_patients():
        record = get_patient_record(patient["patient_id"])
        if record is None:
            continue

        documents.append(
            Document(
                page_content=_format_patient_record(record),
                metadata={
                    "source": "local_his",
                    "document_type": "patient_record",
                    "patient_id": patient["patient_id"],
                    "patient_name": patient["name"],
                },
            )
        )

    return documents


def serialize_documents(documents: list[Document]) -> list[dict]:
    return [
        {
            "page_content": document.page_content,
            "metadata": document.metadata,
        }
        for document in documents
    ]

