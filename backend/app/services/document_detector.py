import re
from typing import Dict


DOCUMENT_TYPES = [
    "Aadhaar",
    "PAN",
    "Passport",
    "Driving Licence",
    "Voter ID",
    "GST",
    "Visa",
    "Unknown",
]


def normalize_text(text: str) -> str:
    return " ".join((text or "").upper().split())


def detect_document_type(text: str) -> Dict:
    """
    Detect document type from OCR text using rule-based signals.

    Returns:
        {
            "detected": str,
            "confidence": float,
            "signals": list[str]
        }
    """

    normalized = normalize_text(text)

    if not normalized:
        return {
            "detected": "Unknown",
            "confidence": 0.0,
            "signals": ["NO_OCR_TEXT"],
        }

    scores = {
        "Aadhaar": 0,
        "PAN": 0,
        "Passport": 0,
        "Driving Licence": 0,
        "Voter ID": 0,
        "GST": 0,
        "Visa": 0,
    }

    signals = []

    # ---------------------------------
    # AADHAAR
    # ---------------------------------
    if "AADHAAR" in normalized:
        scores["Aadhaar"] += 5
        signals.append("AADHAAR_KEYWORD")

    if "UNIQUE IDENTIFICATION AUTHORITY" in normalized:
        scores["Aadhaar"] += 4
        signals.append("UIDAI_KEYWORD")

    if re.search(r"\b\d{4}\s?\d{4}\s?\d{4}\b", normalized):
        scores["Aadhaar"] += 4
        signals.append("12_DIGIT_ID_PATTERN")

    # ---------------------------------
    # PAN
    # ---------------------------------
    if "INCOME TAX DEPARTMENT" in normalized:
        scores["PAN"] += 5
        signals.append("INCOME_TAX_KEYWORD")

    if "PERMANENT ACCOUNT NUMBER" in normalized:
        scores["PAN"] += 5
        signals.append("PAN_KEYWORD")

    if re.search(r"\b[A-Z]{5}\d{4}[A-Z]\b", normalized):
        scores["PAN"] += 5
        signals.append("PAN_NUMBER_PATTERN")

    # ---------------------------------
    # PASSPORT
    # ---------------------------------
    if "PASSPORT" in normalized:
        scores["Passport"] += 6
        signals.append("PASSPORT_KEYWORD")

    if "REPUBLIC OF INDIA" in normalized:
        scores["Passport"] += 3
        signals.append("INDIA_PASSPORT_HEADER")

    if "P<IND" in normalized or "P<" in normalized:
        scores["Passport"] += 4
        signals.append("PASSPORT_MRZ_PATTERN")

    # ---------------------------------
    # DRIVING LICENCE
    # ---------------------------------
    if "DRIVING LICENCE" in normalized:
        scores["Driving Licence"] += 6
        signals.append("DRIVING_LICENCE_KEYWORD")

    if "DRIVING LICENSE" in normalized:
        scores["Driving Licence"] += 6
        signals.append("DRIVING_LICENSE_KEYWORD")

    if "TRANSPORT" in normalized:
        scores["Driving Licence"] += 2
        signals.append("TRANSPORT_KEYWORD")

    if "DL NO" in normalized or "DL NO." in normalized:
        scores["Driving Licence"] += 4
        signals.append("DL_NUMBER_KEYWORD")

    # ---------------------------------
    # VOTER ID
    # ---------------------------------
    if "ELECTION COMMISSION OF INDIA" in normalized:
        scores["Voter ID"] += 6
        signals.append("ECI_KEYWORD")

    if "VOTER" in normalized:
        scores["Voter ID"] += 3
        signals.append("VOTER_KEYWORD")

    if re.search(r"\b[A-Z]{3}\d{7}\b", normalized):
        scores["Voter ID"] += 3
        signals.append("EPIC_PATTERN")

    # ---------------------------------
    # GST
    # ---------------------------------
    if "GSTIN" in normalized:
        scores["GST"] += 6
        signals.append("GSTIN_KEYWORD")

    if "GOODS AND SERVICES TAX" in normalized:
        scores["GST"] += 5
        signals.append("GST_KEYWORD")

    if re.search(
        r"\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9]Z[A-Z0-9]\b",
        normalized,
    ):
        scores["GST"] += 6
        signals.append("GSTIN_PATTERN")

    # ---------------------------------
    # VISA
    # ---------------------------------
    if "VISA" in normalized:
        scores["Visa"] += 5
        signals.append("VISA_KEYWORD")

    if "EMBASSY" in normalized:
        scores["Visa"] += 3
        signals.append("EMBASSY_KEYWORD")

    if "CONSULATE" in normalized:
        scores["Visa"] += 3
        signals.append("CONSULATE_KEYWORD")

    # ---------------------------------
    # SELECT BEST MATCH
    # ---------------------------------
    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]

    if best_score == 0:
        return {
            "detected": "Unknown",
            "confidence": 0.0,
            "signals": [],
        }

    # Convert rule score into a simple confidence value.
    confidence = min(best_score * 10, 100)

    return {
        "detected": best_type,
        "confidence": float(confidence),
        "signals": signals,
    }