
from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
import requests
import os
from PyPDF2 import PdfReader
from urllib.parse import urlparse, parse_qs
import re
from langdetect import detect
from deep_translator import GoogleTranslator

app = FastAPI()

class FileInput(BaseModel):
    url: str  # PDF link from Google Drive, OneDrive, or direct EOC link

measure_weights = {
    "Breast Cancer Screening": 1.5,
    "Colorectal Cancer Screening": 1.5,
    "Annual Flu Vaccine": 1,
    "Pneumonia Vaccination": 1,
    "Monitoring Physical Activity": 1,
    "Adult BMI Assessment": 1,
    "Diabetes Care – Eye Exam": 1.5,
    "Diabetes Care – Kidney Monitoring": 1.5,
    "Diabetes Care – Blood Sugar Controlled": 3,
    "Controlling Blood Pressure": 3,
    "Rheumatoid Arthritis Management": 1.5,
    "Osteoporosis Management Post‑Fracture": 1.5,
    "Pain Assessment": 1,
    "Reducing the Risk of Falling": 1,
    "Medication Reconciliation Post‑Discharge": 1,
    "Statin Therapy for Cardiovascular Disease": 1.5,
    "Complaints About the Health/Drug Plan": 1.5,
    "Members Choosing to Leave the Plan": 1.5,
    "Plan Makes Timely Decisions About Appeals": 1.5,
    "Reviewing Appeals Decisions": 1.5,
    "Customer Service": 1.5,
    "Call Center – Foreign Language Interpreter Availability": 1,
    "Call Center – TTY Availability": 1,
    "Drug Plan Customer Service": 1.5,
    "Formulary Accuracy": 1.5,
    "Prior Authorization & Pharmacy Network Info": 1.5,
    "MTM Program Availability": 1.5,
    "Disenrollment Info": 1.5,
    "Access to Care": 1.5,
    "Care Coordination": 1.5,
    "Appointment Availability": 1.5,
    "Needed Care": 1.5
}

keyword_to_measure = {
    "flu vaccine": "Annual Flu Vaccine",
    "pneumonia": "Pneumonia Vaccination",
    "breast cancer": "Breast Cancer Screening",
    "colorectal cancer": "Colorectal Cancer Screening",
    "colonoscopy": "Colorectal Cancer Screening",
    "bmi": "Adult BMI Assessment",
    "physical activity": "Monitoring Physical Activity",
    "eye exam": "Diabetes Care – Eye Exam",
    "kidney": "Diabetes Care – Kidney Monitoring",
    "blood sugar": "Diabetes Care – Blood Sugar Controlled",
    "a1c": "Diabetes Care – Blood Sugar Controlled",
    "hypertension": "Controlling Blood Pressure",
    "blood pressure": "Controlling Blood Pressure",
    "arthritis": "Rheumatoid Arthritis Management",
    "osteoporosis": "Osteoporosis Management Post‑Fracture",
    "pain": "Pain Assessment",
    "falls": "Reducing the Risk of Falling",
    "medication reconciliation": "Medication Reconciliation Post‑Discharge",
    "statin": "Statin Therapy for Cardiovascular Disease",
    "complaint": "Complaints About the Health/Drug Plan",
    "disenroll": "Members Choosing to Leave the Plan",
    "appeal": "Plan Makes Timely Decisions About Appeals",
    "reviewing appeals": "Reviewing Appeals Decisions",
    "customer service": "Customer Service",
    "foreign language": "Call Center – Foreign Language Interpreter Availability",
    "tty": "Call Center – TTY Availability",
    "drug plan customer service": "Drug Plan Customer Service",
    "formulary": "Formulary Accuracy",
    "drug list": "Formulary Accuracy",
    "prior authorization": "Prior Authorization & Pharmacy Network Info",
    "pharmacy network": "Prior Authorization & Pharmacy Network Info",
    "mtm": "MTM Program Availability",
    "access to care": "Access to Care",
    "care coordination": "Care Coordination",
    "appointment": "Appointment Availability",
    "needed care": "Needed Care",
    # SCAN multilingual documents often mention these too:
    "interpreters": "Call Center – Foreign Language Interpreter Availability",
    "translation services": "Call Center – Foreign Language Interpreter Availability"
}

def calculate_star_rating(text: str) -> float:
    try:
        lang = detect(text)
    except:
        lang = "en"

    # Translate if not in English
    if lang != "en":
        try:
            text = GoogleTranslator(source='auto', target='en').translate(text)
        except Exception:
            raise HTTPException(status_code=500, detail="Translation failed.")

    text = text.lower()
    matched_measures = set()

    for keyword, measure in keyword_to_measure.items():
        if re.search(rf"\b{re.escape(keyword)}\b", text):
            matched_measures.add(measure)

    matched_score = sum(measure_weights[m] for m in matched_measures)
    total_possible_score = sum(measure_weights.values())  # 45.5
    max_eoc_star_rating = 3.7

    normalized_score = (matched_score / total_possible_score) * max_eoc_star_rating
    return round(normalized_score, 2)

def extract_file_url(link: str) -> str:
    if "drive.google.com" in link:
        try:
            if "/file/d/" in link:
                file_id = link.split("/file/d/")[1].split("/")[0]
            elif "open?id=" in link:
                query = parse_qs(urlparse(link).query)
                file_id = query.get("id", [None])[0]
            if not file_id:
                raise HTTPException(status_code=400, detail="Invalid Google Drive URL.")
            return f"https://drive.google.com/uc?export=download&id={file_id}"
        except:
            raise HTTPException(status_code=400, detail="Google Drive parsing error.")
    elif any(domain in link.lower() for domain in ["onedrive", "1drv.ms", "microsoftpersonalcontent.com"]):
        try:
            return requests.get(link, allow_redirects=True, timeout=10).url
        except:
            raise HTTPException(status_code=400, detail="Unable to resolve OneDrive link.")
    elif any(domain in link.lower() for domain in [
        "scanhealthplan.com", "cigna.com", "uhc.com", "humana.com"
    ]) or link.lower().endswith(".pdf"):
        return link
    else:
        raise HTTPException(status_code=400, detail="Unsupported file source.")

@app.post("/calculate-star-rating", response_class=PlainTextResponse)
def calculate_rating(input: FileInput):
    try:
        url = extract_file_url(input.url)
        session = requests.Session()
        session.mount("https://", requests.adapters.HTTPAdapter(max_retries=3))

        response = session.get(url, timeout=15, verify=False)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to download PDF.")

        if not response.content.startswith(b"%PDF"):
            raise HTTPException(status_code=400, detail="Downloaded file is not a valid PDF.")

        with open("temp_eoc.pdf", "wb") as f:
            f.write(response.content)

        reader = PdfReader("temp_eoc.pdf")
        text = " ".join([page.extract_text() or "" for page in reader.pages])
        os.remove("temp_eoc.pdf")

        rating = calculate_star_rating(text)
        return str(rating)

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
