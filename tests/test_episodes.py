import unittest

from app.rag.episodes import EPISODE_STRATEGY, build_patient_episodes, compact_episode_timeline


class EpisodeBuilderTests(unittest.TestCase):
    def test_build_patient_episodes_groups_same_date_clinical_data(self) -> None:
        record = {
            "patient": {"patient_id": "PX01", "name": "Test Patient"},
            "encounters": [
                {
                    "encounter_id": "EX01",
                    "date": "2026-01-10",
                    "visit_type": "Outpatient",
                    "chief_complaint": "Fatigue",
                    "diagnosis": "Anemia",
                },
                {
                    "encounter_id": "EX02",
                    "date": "2026-02-10",
                    "visit_type": "Follow-up",
                    "chief_complaint": "Review",
                    "diagnosis": "Anemia",
                },
            ],
            "labs": [
                {
                    "lab_id": "LX01",
                    "date": "2026-01-10",
                    "test_name": "Hemoglobin",
                    "value": "9.8",
                    "unit": "g/dL",
                    "reference_range": "12-16",
                }
            ],
            "medications": [
                {
                    "medication_id": "MX01",
                    "drug_name": "Iron",
                    "dose": "100 mg",
                    "frequency": "Once daily",
                    "start_date": "2026-02-10",
                }
            ],
            "clinical_notes": [
                {
                    "note_id": "NX01",
                    "date": "2026-01-10",
                    "note_type": "Progress note",
                    "note_text": "Patient reports fatigue.",
                }
            ],
        }

        packet = build_patient_episodes(record)

        self.assertEqual(packet["episode_strategy"], EPISODE_STRATEGY)
        self.assertEqual(packet["episode_count"], 2)
        self.assertEqual(packet["episodes"][0]["episode_id"], "PX01-E01")
        self.assertEqual(packet["episodes"][0]["source_ids"]["encounters"], ["EX01"])
        self.assertEqual(packet["episodes"][0]["source_ids"]["labs"], ["LX01"])
        self.assertEqual(packet["episodes"][0]["source_ids"]["clinical_notes"], ["NX01"])
        self.assertEqual(packet["episodes"][1]["source_ids"]["medications"], ["MX01"])
        self.assertIn("PX01-E01", packet["episodes"][1]["transition_from_previous"])

    def test_compact_episode_timeline_exposes_sources_without_full_notes(self) -> None:
        record = {
            "patient": {"patient_id": "PX01"},
            "encounters": [
                {
                    "encounter_id": "EX01",
                    "date": "2026-01-10",
                    "visit_type": "Outpatient",
                    "chief_complaint": "Fatigue",
                    "diagnosis": "Anemia",
                }
            ],
            "labs": [],
            "medications": [],
            "clinical_notes": [
                {
                    "note_id": "NX01",
                    "date": "2026-01-10",
                    "note_type": "Progress note",
                    "note_text": "Full note stays out of compact timeline.",
                }
            ],
        }

        timeline = compact_episode_timeline(record)

        self.assertEqual(timeline[0]["episode_id"], "PX01-E01")
        self.assertIn("source_ids", timeline[0])
        self.assertNotIn("clinical_notes", timeline[0])


if __name__ == "__main__":
    unittest.main()
