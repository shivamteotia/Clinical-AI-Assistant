import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = BASE_DIR / "his.db"


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _rows(cursor: sqlite3.Cursor) -> list[dict]:
    return [dict(row) for row in cursor.fetchall()]


def list_patients() -> list[dict]:
    with _connect() as connection:
        cursor = connection.execute(
            """
            SELECT patient_id, name, age, gender, phone, address
            FROM patients
            ORDER BY patient_id
            """
        )
        return _rows(cursor)


def get_patient(patient_id: str) -> dict | None:
    with _connect() as connection:
        cursor = connection.execute(
            """
            SELECT patient_id, name, age, gender, phone, address
            FROM patients
            WHERE patient_id = ?
            """,
            (patient_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_patient_record(patient_id: str) -> dict | None:
    patient = get_patient(patient_id)
    if patient is None:
        return None

    with _connect() as connection:
        encounters = _rows(
            connection.execute(
                """
                SELECT encounter_id, date, visit_type, chief_complaint, diagnosis
                FROM encounters
                WHERE patient_id = ?
                ORDER BY date DESC
                """,
                (patient_id,),
            )
        )
        labs = _rows(
            connection.execute(
                """
                SELECT lab_id, date, test_name, value, unit, reference_range
                FROM labs
                WHERE patient_id = ?
                ORDER BY date DESC
                """,
                (patient_id,),
            )
        )
        medications = _rows(
            connection.execute(
                """
                SELECT medication_id, drug_name, dose, frequency, start_date
                FROM medications
                WHERE patient_id = ?
                ORDER BY start_date DESC
                """,
                (patient_id,),
            )
        )
        notes = _rows(
            connection.execute(
                """
                SELECT note_id, date, note_type, note_text
                FROM clinical_notes
                WHERE patient_id = ?
                ORDER BY date DESC
                """,
                (patient_id,),
            )
        )

    return {
        "patient": patient,
        "encounters": encounters,
        "labs": labs,
        "medications": medications,
        "clinical_notes": notes,
    }

