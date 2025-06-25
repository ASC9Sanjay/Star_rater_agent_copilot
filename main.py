# from fastapi import FastAPI, HTTPException, Query
# from fastapi.responses import JSONResponse
# import requests
# import os
# import ssl
# from PyPDF2 import PdfReader

# app = FastAPI()

# def calculate_star_rating(text: str) -> float:
#     text = text.lower()
#     score = 0

#     # Medicare EOC-based categories
#     keywords = {
#         "preventive care": 1,
#         "screening": 1,
#         "vaccines": 1,
#         "chronic condition": 1,
#         "diabetes": 1,
#         "hypertension": 1,
#         "customer service": 1,
#         "call center": 1,
#         "member satisfaction": 1,
#         "grievance": 1,
#         "drug safety": 1,
#         "medication review": 1,
#     }

#     for keyword in keywords:
#         if keyword in text:
#             score += 1

#     max_score = len(keywords)
#     rating = round((score / max_score) * 5, 1) if max_score else 0.0
#     return rating

# @app.get("/get-star-rating/")
# def get_star_rating(drive_link: str = Query(..., description="Public Google Drive share link to EOC PDF")):
#     try:
#         # Extract file ID
#         try:
#             file_id = drive_link.split('/d/')[1].split('/')[0]
#         except IndexError:
#             raise HTTPException(status_code=400, detail="Invalid Google Drive link format.")

#         download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

#         # Set up SSL fix
#         session = requests.Session()
#         adapter = requests.adapters.HTTPAdapter(max_retries=3)
#         session.mount("https://", adapter)
#         session.verify = ssl.get_default_verify_paths().cafile

#         # Download file
#         # response = session.get(download_url, timeout=10)
#         response = session.get(download_url, timeout=10, verify=False)

#         if response.status_code != 200:
#             raise HTTPException(status_code=400, detail="Failed to download file from Google Drive.")

#         # Save file locally
#         temp_path = "temp_eoc.pdf"
#         with open(temp_path, "wb") as f:
#             f.write(response.content)

#         # Extract text
#         reader = PdfReader(temp_path)
#         text = " ".join([page.extract_text() or "" for page in reader.pages])
#         os.remove(temp_path)

#         # Calculate rating
#         rating = calculate_star_rating(text)
#         return JSONResponse(content={"star_rating": rating})

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))



from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import requests
import os
from PyPDF2 import PdfReader
from urllib.parse import urlparse, parse_qs

app = FastAPI()

class FileInput(BaseModel):
    url: str  # PDF link from Google Drive or OneDrive

# Improved keyword-based scoring
def calculate_star_rating(text: str) -> float:
    text = text.lower()
    score = 0

    keywords = {
        "preventive care": 10,
        "screening": 10,
        "vaccines": 5,
        "chronic condition": 15,
        "diabetes": 10,
        "hypertension": 10,
        "customer service": 10,
        "call center": 5,
        "member satisfaction": 10,
        "grievance": 5,
        "drug safety": 5,
        "medication review": 5,
    }

    max_score = sum(keywords.values())
    matched_score = 0

    for keyword, weight in keywords.items():
        if keyword in text:
            matched_score += weight

    rating = round((matched_score / max_score) * 5, 1) if max_score else 0.0
    return rating

# ✅ Improved auto-conversion of Google Drive and OneDrive links
def extract_file_url(link: str) -> str:
    if "drive.google.com" in link:
        # Handle different types of Drive URLs
        try:
            if "/file/d/" in link:
                # Format: https://drive.google.com/file/d/FILE_ID/view
                file_id = link.split("/file/d/")[1].split("/")[0]
            elif "open?id=" in link:
                # Format: https://drive.google.com/open?id=FILE_ID
                query = parse_qs(urlparse(link).query)
                file_id = query.get("id", [None])[0]
            else:
                raise HTTPException(status_code=400, detail="Unsupported Google Drive URL format.")

            if not file_id:
                raise HTTPException(status_code=400, detail="Could not extract file ID from Google Drive URL.")

            return f"https://drive.google.com/uc?export=download&id={file_id}"
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Google Drive link format.")

    elif "1drv.ms" in link or "onedrive.live.com" in link:
        try:
            if "1drv.ms" in link:
                # Short link that redirects to actual OneDrive URL
                response = requests.get(link, allow_redirects=True)
                link = response.url

            parsed = urlparse(link)
            base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            return base_url + "?download=1"
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid OneDrive link format.")

    else:
        raise HTTPException(status_code=400, detail="Only Google Drive and OneDrive links are supported.")

@app.post("/calculate-star-rating")
def calculate_rating(input: FileInput):
    try:
        # Auto-convert to direct download link
        download_url = extract_file_url(input.url)

        # Robust session with retry
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(max_retries=3)
        session.mount("https://", adapter)

        response = session.get(download_url, timeout=10, verify=False)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to download file from the link.")

        # Temporarily save and read the PDF
        temp_path = "temp_eoc.pdf"
        with open(temp_path, "wb") as f:
            f.write(response.content)

        reader = PdfReader(temp_path)
        text = " ".join([page.extract_text() or "" for page in reader.pages])
        os.remove(temp_path)

        # Calculate star rating from PDF content
        rating = calculate_star_rating(text)
        return JSONResponse(content={"star_rating": rating})

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


