import json
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
NOTES_DIR = DATA_DIR / "notes"
DB_PATH = BASE_DIR / "his.db"


def load_json(filename: str) -> list[dict]:
    with open(DATA_DIR / filename, "r", encoding="utf-8") as file:
        return json.load(file)


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        DROP TABLE IF EXISTS clinical_notes;
        DROP TABLE IF EXISTS medications;
        DROP TABLE IF EXISTS labs;
        DROP TABLE IF EXISTS encounters;
        DROP TABLE IF EXISTS patients;

        CREATE TABLE patients (
            patient_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            age INTEGER NOT NULL,
            gender TEXT NOT NULL,
            phone TEXT NOT NULL,
            address TEXT NOT NULL
        );

        CREATE TABLE encounters (
            encounter_id TEXT PRIMARY KEY,
            patient_id TEXT NOT NULL,
            date TEXT NOT NULL,
            visit_type TEXT NOT NULL,
            chief_complaint TEXT NOT NULL,
            diagnosis TEXT NOT NULL,
            FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
        );

        CREATE TABLE labs (
            lab_id TEXT PRIMARY KEY,
            patient_id TEXT NOT NULL,
            date TEXT NOT NULL,
            test_name TEXT NOT NULL,
            value TEXT NOT NULL,
            unit TEXT NOT NULL,
            reference_range TEXT NOT NULL,
            FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
        );

        CREATE TABLE medications (
            medication_id TEXT PRIMARY KEY,
            patient_id TEXT NOT NULL,
            drug_name TEXT NOT NULL,
            dose TEXT NOT NULL,
            frequency TEXT NOT NULL,
            start_date TEXT NOT NULL,
            FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
        );

        CREATE TABLE clinical_notes (
            note_id TEXT PRIMARY KEY,
            patient_id TEXT NOT NULL,
            date TEXT NOT NULL,
            note_type TEXT NOT NULL,
            note_text TEXT NOT NULL,
            source_file TEXT NOT NULL,
            FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
        );
        """
    )


def seed_patients(connection: sqlite3.Connection) -> None:
    for patient in load_json("patients.json"):
        connection.execute(
            """
            INSERT INTO patients (patient_id, name, age, gender, phone, address)
            VALUES (:patient_id, :name, :age, :gender, :phone, :address)
            """,
            patient,
        )


def seed_encounters(connection: sqlite3.Connection) -> None:
    for encounter in load_json("encounters.json"):
        connection.execute(
            """
            INSERT INTO encounters (
                encounter_id, patient_id, date, visit_type, chief_complaint, diagnosis
            )
            VALUES (
                :encounter_id, :patient_id, :date, :visit_type, :chief_complaint, :diagnosis
            )
            """,
            encounter,
        )


def seed_labs(connection: sqlite3.Connection) -> None:
    for lab in load_json("labs.json"):
        connection.execute(
            """
            INSERT INTO labs (lab_id, patient_id, date, test_name, value, unit, reference_range)
            VALUES (:lab_id, :patient_id, :date, :test_name, :value, :unit, :reference_range)
            """,
            lab,
        )


def seed_medications(connection: sqlite3.Connection) -> None:
    for medication in load_json("medications.json"):
        connection.execute(
            """
            INSERT INTO medications (
                medication_id, patient_id, drug_name, dose, frequency, start_date
            )
            VALUES (
                :medication_id, :patient_id, :drug_name, :dose, :frequency, :start_date
            )
            """,
            medication,
        )


def seed_notes(connection: sqlite3.Connection) -> None:
    for index, note_path in enumerate(sorted(NOTES_DIR.glob("*.txt")), start=1):
        patient_id = note_path.stem.split("_")[0]
        note_text = note_path.read_text(encoding="utf-8")
        connection.execute(
            """
            INSERT INTO clinical_notes (
                note_id, patient_id, date, note_type, note_text, source_file
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"N{index:03d}",
                patient_id,
                "2026-02-20",
                "Progress note",
                note_text,
                note_path.name,
            ),
        )


def main() -> None:
    with sqlite3.connect(DB_PATH) as connection:
        create_schema(connection)
        seed_patients(connection)
        seed_encounters(connection)
        seed_labs(connection)
        seed_medications(connection)
        seed_notes(connection)
        connection.commit()

    print(f"Seeded local HIS database: {DB_PATH}")


if __name__ == "__main__":
    main()

