import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
NOTES_DIR = DATA_DIR / "notes"


CASES = [
    {
        "patient_id": "P001",
        "name": "Aarav Sharma",
        "age": 52,
        "gender": "Male",
        "address": "Mumbai, Maharashtra",
        "chief_complaint": "Increased thirst and fatigue",
        "diagnosis": "Type 2 diabetes mellitus",
        "medication": ("Metformin", "500 mg", "Twice daily"),
        "labs": [("HbA1c", "8.2", "%", "< 5.7"), ("Fasting glucose", "168", "mg/dL", "70-99")],
        "note": "Patient reports increased thirst, frequent urination, and fatigue for the last three months. Lifestyle counseling provided. Started on metformin and advised dietary modification, glucose monitoring, and follow-up in four weeks.",
    },
    {
        "patient_id": "P002",
        "name": "Meera Iyer",
        "age": 44,
        "gender": "Female",
        "address": "Bengaluru, Karnataka",
        "chief_complaint": "Intermittent wheezing and cough",
        "diagnosis": "Bronchial asthma",
        "medication": ("Salbutamol inhaler", "100 mcg", "As needed"),
        "labs": [],
        "note": "Patient reports intermittent wheezing, cough, and mild breathlessness, worse at night and after dust exposure. No fever or chest pain. Salbutamol inhaler prescribed as rescue medication. Advised trigger avoidance.",
    },
    {
        "patient_id": "P003",
        "name": "Rohan Das",
        "age": 67,
        "gender": "Male",
        "address": "Kolkata, West Bengal",
        "chief_complaint": "Chest discomfort and shortness of breath",
        "diagnosis": "Hypertension with suspected angina",
        "medication": ("Amlodipine", "5 mg", "Once daily"),
        "labs": [("Troponin I", "0.02", "ng/mL", "< 0.04")],
        "note": "Patient presented with chest discomfort and shortness of breath. Blood pressure elevated at presentation. Initial troponin within reference range. ECG monitoring advised and cardiology evaluation recommended.",
    },
    {
        "patient_id": "P004",
        "name": "Nisha Patel",
        "age": 38,
        "gender": "Female",
        "address": "Ahmedabad, Gujarat",
        "chief_complaint": "Burning urination and fever",
        "diagnosis": "Urinary tract infection",
        "medication": ("Nitrofurantoin", "100 mg", "Twice daily"),
        "labs": [("Urine leukocytes", "Positive", "", "Negative"), ("Temperature", "38.4", "C", "36.5-37.5")],
        "note": "Patient has burning urination, urinary frequency, and fever for two days. Urine dipstick showed leukocytes. Hydration advice given and antibiotic course started.",
    },
    {
        "patient_id": "P005",
        "name": "Kabir Khan",
        "age": 61,
        "gender": "Male",
        "address": "Delhi",
        "chief_complaint": "Chronic cough and exertional breathlessness",
        "diagnosis": "Chronic obstructive pulmonary disease",
        "medication": ("Tiotropium inhaler", "18 mcg", "Once daily"),
        "labs": [("SpO2", "93", "%", "95-100")],
        "note": "Patient reports chronic cough, sputum production, and exertional breathlessness. Smoking history noted in dummy record. Inhaler technique reviewed and pulmonary follow-up advised.",
    },
    {
        "patient_id": "P006",
        "name": "Ananya Rao",
        "age": 29,
        "gender": "Female",
        "address": "Hyderabad, Telangana",
        "chief_complaint": "Palpitations and weight loss",
        "diagnosis": "Hyperthyroidism",
        "medication": ("Carbimazole", "10 mg", "Twice daily"),
        "labs": [("TSH", "0.02", "mIU/L", "0.4-4.0"), ("Free T4", "2.4", "ng/dL", "0.8-1.8")],
        "note": "Patient reports palpitations, heat intolerance, tremor, and unintentional weight loss. Thyroid labs reviewed and endocrinology follow-up advised.",
    },
    {
        "patient_id": "P007",
        "name": "Vikram Singh",
        "age": 58,
        "gender": "Male",
        "address": "Jaipur, Rajasthan",
        "chief_complaint": "Headache and high blood pressure",
        "diagnosis": "Essential hypertension",
        "medication": ("Telmisartan", "40 mg", "Once daily"),
        "labs": [("Blood pressure", "158/96", "mmHg", "< 120/80")],
        "note": "Patient seen for headache and repeated high blood pressure readings. Salt reduction and home blood pressure log discussed. Antihypertensive medication started.",
    },
    {
        "patient_id": "P008",
        "name": "Farah Ali",
        "age": 33,
        "gender": "Female",
        "address": "Lucknow, Uttar Pradesh",
        "chief_complaint": "Fatigue and pallor",
        "diagnosis": "Iron deficiency anemia",
        "medication": ("Ferrous sulfate", "325 mg", "Once daily"),
        "labs": [("Hemoglobin", "9.8", "g/dL", "12-16"), ("Ferritin", "8", "ng/mL", "15-150")],
        "note": "Patient reports fatigue, dizziness, and pallor. Labs show low hemoglobin and ferritin. Iron supplementation started and dietary counseling provided.",
    },
    {
        "patient_id": "P009",
        "name": "Suresh Nair",
        "age": 72,
        "gender": "Male",
        "address": "Kochi, Kerala",
        "chief_complaint": "Reduced urine output and swelling",
        "diagnosis": "Chronic kidney disease",
        "medication": ("Furosemide", "20 mg", "Once daily"),
        "labs": [("Creatinine", "2.1", "mg/dL", "0.7-1.3"), ("eGFR", "34", "mL/min/1.73m2", "> 60")],
        "note": "Patient reports reduced urine output and ankle swelling. Creatinine is elevated in the dummy record and eGFR is reduced. Nephrology review advised.",
    },
    {
        "patient_id": "P010",
        "name": "Pooja Menon",
        "age": 26,
        "gender": "Female",
        "address": "Chennai, Tamil Nadu",
        "chief_complaint": "Missed periods and nausea",
        "diagnosis": "Early pregnancy",
        "medication": ("Folic acid", "5 mg", "Once daily"),
        "labs": [("Urine pregnancy test", "Positive", "", "Negative")],
        "note": "Patient reports missed periods, nausea, and breast tenderness. Urine pregnancy test is positive. Antenatal counseling and obstetric follow-up advised.",
    },
    {
        "patient_id": "P011",
        "name": "Aditya Verma",
        "age": 47,
        "gender": "Male",
        "address": "Pune, Maharashtra",
        "chief_complaint": "Epigastric pain and acidity",
        "diagnosis": "Gastroesophageal reflux disease",
        "medication": ("Pantoprazole", "40 mg", "Once daily"),
        "labs": [],
        "note": "Patient reports epigastric burning, sour regurgitation, and symptoms after spicy meals. Lifestyle advice and proton pump inhibitor therapy started.",
    },
    {
        "patient_id": "P012",
        "name": "Leela Thomas",
        "age": 64,
        "gender": "Female",
        "address": "Thiruvananthapuram, Kerala",
        "chief_complaint": "Knee pain and stiffness",
        "diagnosis": "Osteoarthritis of knee",
        "medication": ("Paracetamol", "650 mg", "As needed"),
        "labs": [],
        "note": "Patient reports bilateral knee pain, morning stiffness, and difficulty climbing stairs. Weight management and physiotherapy were discussed.",
    },
    {
        "patient_id": "P013",
        "name": "Imran Sheikh",
        "age": 41,
        "gender": "Male",
        "address": "Bhopal, Madhya Pradesh",
        "chief_complaint": "Fever with chills",
        "diagnosis": "Malaria",
        "medication": ("Artemether lumefantrine", "20/120 mg", "As per schedule"),
        "labs": [("Malaria parasite smear", "Positive", "", "Negative"), ("Platelets", "118000", "/uL", "150000-450000")],
        "note": "Patient reports fever with chills and body ache. Peripheral smear is positive for malaria parasite in dummy data. Antimalarial treatment started.",
    },
    {
        "patient_id": "P014",
        "name": "Tanya Roy",
        "age": 36,
        "gender": "Female",
        "address": "Guwahati, Assam",
        "chief_complaint": "Low mood and poor sleep",
        "diagnosis": "Depressive symptoms",
        "medication": ("Sertraline", "25 mg", "Once daily"),
        "labs": [],
        "note": "Patient reports persistent low mood, poor sleep, reduced interest, and fatigue. Safety screening documented in dummy record. Mental health follow-up advised.",
    },
    {
        "patient_id": "P015",
        "name": "Manoj Gupta",
        "age": 55,
        "gender": "Male",
        "address": "Patna, Bihar",
        "chief_complaint": "Right upper abdominal pain",
        "diagnosis": "Gallstone disease",
        "medication": ("Drotaverine", "80 mg", "As needed"),
        "labs": [("Total bilirubin", "1.0", "mg/dL", "0.1-1.2")],
        "note": "Patient reports right upper abdominal pain after fatty meals. Ultrasound note mentions gallstones in dummy data. Surgical review advised.",
    },
    {
        "patient_id": "P016",
        "name": "Sneha Kapoor",
        "age": 31,
        "gender": "Female",
        "address": "Noida, Uttar Pradesh",
        "chief_complaint": "Migraine headaches",
        "diagnosis": "Migraine",
        "medication": ("Sumatriptan", "50 mg", "As needed"),
        "labs": [],
        "note": "Patient reports unilateral throbbing headache with nausea and light sensitivity. Trigger diary and acute migraine medication discussed.",
    },
    {
        "patient_id": "P017",
        "name": "Harish Kulkarni",
        "age": 69,
        "gender": "Male",
        "address": "Nagpur, Maharashtra",
        "chief_complaint": "Memory difficulty",
        "diagnosis": "Mild cognitive impairment",
        "medication": ("Donepezil", "5 mg", "Once daily"),
        "labs": [("Vitamin B12", "420", "pg/mL", "200-900")],
        "note": "Patient and family report recent memory difficulty and missed appointments. Cognitive screening performed in dummy record. Neurology follow-up advised.",
    },
    {
        "patient_id": "P018",
        "name": "Ritu Bansal",
        "age": 49,
        "gender": "Female",
        "address": "Indore, Madhya Pradesh",
        "chief_complaint": "Joint pain and swelling",
        "diagnosis": "Rheumatoid arthritis",
        "medication": ("Methotrexate", "7.5 mg", "Weekly"),
        "labs": [("Rheumatoid factor", "Positive", "", "Negative"), ("ESR", "42", "mm/hr", "0-20")],
        "note": "Patient reports small joint pain, morning stiffness, and swelling in both hands. Rheumatoid factor positive in dummy data. Rheumatology review advised.",
    },
    {
        "patient_id": "P019",
        "name": "Dev Malhotra",
        "age": 23,
        "gender": "Male",
        "address": "Chandigarh",
        "chief_complaint": "Fever and sore throat",
        "diagnosis": "Viral upper respiratory infection",
        "medication": ("Cetirizine", "10 mg", "Once daily"),
        "labs": [("COVID antigen", "Negative", "", "Negative")],
        "note": "Patient reports fever, sore throat, runny nose, and mild cough. COVID antigen test is negative in dummy data. Symptomatic care advised.",
    },
    {
        "patient_id": "P020",
        "name": "Asha Reddy",
        "age": 57,
        "gender": "Female",
        "address": "Visakhapatnam, Andhra Pradesh",
        "chief_complaint": "Tingling feet and numbness",
        "diagnosis": "Peripheral neuropathy",
        "medication": ("Pregabalin", "75 mg", "At night"),
        "labs": [("Vitamin B12", "180", "pg/mL", "200-900")],
        "note": "Patient reports tingling feet, numbness, and burning sensation at night. Vitamin B12 is low in dummy data. Neuropathy assessment documented.",
    },
]


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    NOTES_DIR.mkdir(exist_ok=True)
    for note_path in NOTES_DIR.glob("*.txt"):
        note_path.unlink()

    patients = []
    encounters = []
    labs = []
    medications = []

    lab_index = 1
    for index, case in enumerate(CASES, start=1):
        patient_id = case["patient_id"]
        date = f"2026-03-{index:02d}"
        patients.append(
            {
                "patient_id": patient_id,
                "name": case["name"],
                "age": case["age"],
                "gender": case["gender"],
                "phone": f"999000{index:04d}",
                "address": case["address"],
            }
        )
        encounters.append(
            {
                "encounter_id": f"E{index:03d}",
                "patient_id": patient_id,
                "date": date,
                "visit_type": "Outpatient" if index != 3 else "Emergency",
                "chief_complaint": case["chief_complaint"],
                "diagnosis": case["diagnosis"],
            }
        )

        drug_name, dose, frequency = case["medication"]
        medications.append(
            {
                "medication_id": f"M{index:03d}",
                "patient_id": patient_id,
                "drug_name": drug_name,
                "dose": dose,
                "frequency": frequency,
                "start_date": date,
            }
        )

        for test_name, value, unit, reference_range in case["labs"]:
            labs.append(
                {
                    "lab_id": f"L{lab_index:03d}",
                    "patient_id": patient_id,
                    "date": date,
                    "test_name": test_name,
                    "value": value,
                    "unit": unit,
                    "reference_range": reference_range,
                }
            )
            lab_index += 1

        note = (
            f"{case['note']} This is synthetic dummy clinical data for pipeline testing only. "
            f"No real patient information is present."
        )
        (NOTES_DIR / f"{patient_id}_note_001.txt").write_text(note, encoding="utf-8")

    write_json("patients.json", patients)
    write_json("encounters.json", encounters)
    write_json("labs.json", labs)
    write_json("medications.json", medications)

    print(f"Generated {len(patients)} patients")
    print(f"Generated {len(encounters)} encounters")
    print(f"Generated {len(labs)} lab results")
    print(f"Generated {len(medications)} medications")
    print(f"Generated {len(list(NOTES_DIR.glob('*.txt')))} notes")


def write_json(filename: str, rows: list[dict]) -> None:
    with open(DATA_DIR / filename, "w", encoding="utf-8") as file:
        json.dump(rows, file, indent=2)
        file.write("\n")


if __name__ == "__main__":
    main()

