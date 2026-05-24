import unittest

from langchain_core.documents import Document

from app.rag.chunking import chunk_documents
from app.rag.metadata import build_patient_metadata, enrich_chunk_metadata


class MetadataTests(unittest.TestCase):
    def test_build_patient_metadata_extracts_structured_terms(self) -> None:
        metadata = build_patient_metadata({
            "encounters": [{"diagnosis": "Type 2 diabetes mellitus"}],
            "labs": [{"test_name": "HbA1c"}],
            "medications": [{"drug_name": "Metformin"}],
            "clinical_notes": [{"note_type": "Progress note"}],
        })

        self.assertEqual(metadata["diagnoses"], ["Type 2 diabetes mellitus"])
        self.assertIn("hba1c", metadata["lab_terms"])
        self.assertIn("metformin", metadata["medication_terms"])

    def test_enrich_chunk_metadata_adds_source_section_and_mentions(self) -> None:
        metadata = enrich_chunk_metadata(
            "Lab Results:\n- test_name: HbA1c; value: 9.2",
            {
                "lab_tests": ["HbA1c"],
                "diagnoses": [],
                "medications": [],
            },
        )

        self.assertEqual(metadata["source_section"], "labs")
        self.assertEqual(metadata["mentioned_lab_tests"], ["HbA1c"])

    def test_chunk_documents_preserves_structured_metadata(self) -> None:
        chunks = chunk_documents(
            [
                Document(
                    page_content="Medications:\n- drug_name: Metformin; dose: 500 mg",
                    metadata={
                        "patient_id": "P001",
                        "patient_name": "Aarav Sharma",
                        "medications": ["Metformin"],
                        "diagnoses": [],
                        "lab_tests": [],
                    },
                )
            ],
            chunk_size=200,
            chunk_overlap=0,
        )

        self.assertEqual(chunks[0].metadata["source_section"], "medications")
        self.assertEqual(chunks[0].metadata["mentioned_medications"], ["Metformin"])


if __name__ == "__main__":
    unittest.main()
