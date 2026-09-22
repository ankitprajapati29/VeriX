import io
import os
import re
import json
import uuid
import hashlib
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import fitz
import numpy as np
import pytesseract
from app.services.ocr_service import run_ocr as service_run_ocr
from app.services.document_detector import (
    detect_document_type as service_detect_document_type,
)

from app.services.validation_service import (
    validate_aadhaar as service_validate_aadhaar,
    validate_pan as service_validate_pan,
    parse_passport_mrz as service_parse_passport_mrz,
    validate_driving_licence as service_validate_driving_licence,
    validate_voter_id as service_validate_voter_id,
    validate_gstin as service_validate_gstin,
    validate_visa as service_validate_visa,
)
from app.services.risk_engine import calculate_risk as service_calculate_risk
from app.services.forensic_service import analyze_forensics
from PIL import Image, ImageChops, ImageEnhance, ImageFilter
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware


# ============================================================
# VeriX - AI Document & Identity Verification API
# ============================================================

APP_NAME = "VeriX API"
APP_VERSION = "1.0.0"

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_PDF_PAGES = 5
MAX_OCR_TEXT = 25000

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
}

TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

if os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Evidence-based document and identity verification API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:5176",
        "http://127.0.0.1:5176",
],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# VERHOEFF ALGORITHM - AADHAAR
# ============================================================

VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]

VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


def digits_only(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def validate_verhoeff(number: str) -> bool:
    number = digits_only(number)

    if len(number) != 12:
        return False

    checksum = 0

    for index, digit in enumerate(reversed(number)):
        checksum = VERHOEFF_D[
            checksum
        ][
            VERHOEFF_P[index % 8][int(digit)]
        ]

    return checksum == 0


# ============================================================
# GENERAL HELPERS
# ============================================================

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_text(text: str) -> str:
    text = text or ""
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def safe_filename(filename: str) -> str:
    name = Path(filename or "document").name
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)

    if not name:
        name = "document"

    return name[:120]


def file_extension(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def get_file_type(data: bytes) -> str:
    if data.startswith(b"%PDF"):
        return "pdf"

    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"

    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"

    return "unknown"


def validate_magic_bytes(data: bytes, extension: str) -> bool:
    detected = get_file_type(data)

    if extension == ".pdf":
        return detected == "pdf"

    if extension == ".png":
        return detected == "png"

    if extension in {".jpg", ".jpeg"}:
        return detected == "jpeg"

    return False


# ============================================================
# DOCUMENT TYPE DETECTION
# ============================================================

DOCUMENT_TYPES = [
    "Aadhaar",
    "PAN",
    "Driving Licence",
    "Passport",
    "Voter ID",
    "GST",
    "Visa",
    "Unknown",
]


def detect_document_type(text: str) -> str:
    """
    Detect document type using the dedicated document detector service.
    """
    result = service_detect_document_type(text)
    return result.get("detected", "Unknown")

# ============================================================
# OCR
# ============================================================

def preprocess_for_ocr(image: Image.Image) -> Image.Image:
    image = image.convert("RGB")

    max_dimension = 3200

    width, height = image.size

    if max(width, height) > max_dimension:
        scale = max_dimension / max(width, height)

        image = image.resize(
            (
                int(width * scale),
                int(height * scale),
            ),
            Image.Resampling.LANCZOS,
        )

    gray = image.convert("L")

    gray = ImageEnhance.Contrast(gray).enhance(1.5)

    gray = ImageEnhance.Sharpness(gray).enhance(1.3)

    return gray


def run_ocr(image: Image.Image) -> Tuple[str, float]:
    processed = preprocess_for_ocr(image)

    data = pytesseract.image_to_data(
        processed,
        config="--oem 3 --psm 6",
        output_type=pytesseract.Output.DICT,
    )

    words = []
    confidences = []

    for index, word in enumerate(data.get("text", [])):
        word = (word or "").strip()

        if not word:
            continue

        words.append(word)

        try:
            confidence = float(data["conf"][index])

            if confidence >= 0:
                confidences.append(confidence)

        except (ValueError, TypeError, IndexError):
            pass

    text = " ".join(words)

    if not text.strip():
        text = pytesseract.image_to_string(
            processed,
            config="--oem 3 --psm 11",
        )

    if confidences:
        confidence_score = sum(confidences) / len(confidences)
    else:
        confidence_score = 0.0

    return normalize_text(text)[:MAX_OCR_TEXT], round(
        confidence_score,
        2,
    )


def ocr_pdf(data: bytes) -> Tuple[str, float, Optional[Image.Image]]:
    document = fitz.open(stream=data, filetype="pdf")

    all_text = []
    confidence_values = []
    first_page_image = None

    page_count = min(len(document), MAX_PDF_PAGES)

    for page_index in range(page_count):
        page = document[page_index]

        pixmap = page.get_pixmap(
            matrix=fitz.Matrix(2, 2),
            alpha=False,
        )

        image_bytes = pixmap.tobytes("png")

        image = Image.open(
            io.BytesIO(image_bytes)
        ).convert("RGB")

        if first_page_image is None:
            first_page_image = image.copy()

        text, confidence = service_run_ocr(image)
        if text:
            all_text.append(text)

        confidence_values.append(confidence)

    document.close()

    combined_text = normalize_text(
        "\n".join(all_text)
    )[:MAX_OCR_TEXT]

    average_confidence = (
        sum(confidence_values) / len(confidence_values)
        if confidence_values
        else 0.0
    )

    return (
        combined_text,
        round(average_confidence, 2),
        first_page_image,
    )


def ocr_image(data: bytes) -> Tuple[str, float, Image.Image]:
    image = Image.open(
        io.BytesIO(data)
    ).convert("RGB")

    text, confidence = service_run_ocr(image)

    return text, confidence, image


# ============================================================
# IMAGE QUALITY
# ============================================================

def image_quality(image: Image.Image) -> Dict[str, Any]:
    rgb = image.convert("RGB")

    width, height = rgb.size

    gray = np.array(rgb.convert("L"))

    blur_score = float(cv2.Laplacian(
        gray,
        cv2.CV_64F,
    ).var())

    brightness = float(gray.mean())

    issues = []

    if width < 800 or height < 500:
        issues.append("low_resolution")

    if blur_score < 60:
        issues.append("blur_detected")

    if brightness < 45:
        issues.append("too_dark")

    if brightness > 235:
        issues.append("overexposed")

    return {
        "width": width,
        "height": height,
        "blur_score": round(blur_score, 2),
        "brightness": round(brightness, 2),
        "issues": issues,
    }


# ============================================================
# METADATA
# ============================================================

def extract_metadata(image: Image.Image) -> Dict[str, Any]:
    try:
        metadata = image.getexif()

        result = {}

        for key, value in metadata.items():
            result[str(key)] = str(value)[:300]

        return {
            "present": bool(result),
            "fields": result,
        }

    except Exception:
        return {
            "present": False,
            "fields": {},
        }


# ============================================================
# ELA - ERROR LEVEL ANALYSIS
# ============================================================

def analyze_ela(image: Image.Image) -> Dict[str, Any]:
    try:
        original = image.convert("RGB")

        buffer = io.BytesIO()

        original.save(
            buffer,
            format="JPEG",
            quality=90,
        )

        buffer.seek(0)

        recompressed = Image.open(buffer).convert("RGB")

        diff = ImageChops.difference(
            original,
            recompressed,
        )

        extrema = diff.getextrema()

        max_difference = max(
            channel[1]
            for channel in extrema
        )

        difference_array = np.asarray(diff)

        mean_difference = float(
            difference_array.mean()
        )

        # ELA is only a forensic signal.
        suspicious = (
            max_difference > 80
            and mean_difference > 8
        )

        return {
            "available": True,
            "max_difference": int(max_difference),
            "mean_difference": round(
                mean_difference,
                3,
            ),
            "suspicious": suspicious,
        }

    except Exception as exc:
        return {
            "available": False,
            "suspicious": False,
            "error": str(exc),
        }


# ============================================================
# QR DETECTION
# ============================================================

def detect_qr(image: Image.Image) -> Dict[str, Any]:
    try:
        cv_image = cv2.cvtColor(
            np.array(image),
            cv2.COLOR_RGB2BGR,
        )

        detector = cv2.QRCodeDetector()

        data, points, _ = detector.detectAndDecode(
            cv_image
        )

        decoded = bool(data and data.strip())

        return {
            "detected": points is not None,
            "decoded": decoded,
            "data": data[:2000] if decoded else None,
        }

    except Exception as exc:
        return {
            "detected": False,
            "decoded": False,
            "data": None,
            "error": str(exc),
        }


# ============================================================
# AADHAAR
# ============================================================

def extract_aadhaar_number(text: str) -> Optional[str]:
    matches = re.findall(
        r"\b\d{4}\s?\d{4}\s?\d{4}\b",
        text or "",
    )

    for match in matches:
        number = digits_only(match)

        if len(number) == 12:
            return number

    return None


def validate_aadhaar(text: str) -> Dict[str, Any]:
    number = extract_aadhaar_number(text)

    if not number:
        return {
            "number_found": False,
            "format_valid": False,
            "verhoeff_valid": False,
            "status": "NOT_AVAILABLE",
        }

    format_valid = len(number) == 12

    verhoeff_valid = (
        validate_verhoeff(number)
        if format_valid
        else False
    )

    return {
        "number_found": True,
        "masked_number": (
            "XXXX XXXX " + number[-4:]
        ),
        "format_valid": format_valid,
        "verhoeff_valid": verhoeff_valid,
        "status": (
            "VALID"
            if verhoeff_valid
            else "CHECKSUM_FAILED"
        ),
    }


# ============================================================
# PAN
# ============================================================

def extract_pan(text: str) -> Optional[str]:
    match = re.search(
        r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",
        (text or "").upper(),
    )

    return match.group(0) if match else None


def validate_pan(text: str) -> Dict[str, Any]:
    pan = extract_pan(text)

    if not pan:
        return {
            "number_found": False,
            "format_valid": False,
            "status": "NOT_AVAILABLE",
        }

    # PAN has a documented structural pattern.
    # This does NOT prove authenticity.
    format_valid = bool(
        re.fullmatch(
            r"[A-Z]{5}[0-9]{4}[A-Z]",
            pan,
        )
    )

    fourth_character = pan[3]

    fourth_char_valid = fourth_character in (
        "P", "C", "H", "A", "B",
        "G", "J", "L", "F", "T",
    )

    return {
        "number_found": True,
        "masked_pan": pan[:3] + "XXXXX" + pan[-1],
        "format_valid": format_valid,
        "fourth_character": fourth_character,
        "fourth_character_valid": fourth_char_valid,
        "status": (
            "VALID"
            if format_valid and fourth_char_valid
            else "FORMAT_FAILED"
        ),
    }


# ============================================================
# PASSPORT / ICAO MRZ
# ============================================================

ICAO_WEIGHTS = [7, 3, 1]


def mrz_value(char: str) -> int:
    if char == "<":
        return 0

    if char.isdigit():
        return int(char)

    if "A" <= char <= "Z":
        return ord(char) - ord("A") + 10

    return 0


def mrz_check_digit(data: str) -> int:
    total = 0

    for index, char in enumerate(data):
        total += (
            mrz_value(char)
            * ICAO_WEIGHTS[index % 3]
        )

    return total % 10


def validate_mrz_field(
    field: str,
    check_digit: str,
) -> bool:
    if len(check_digit) != 1:
        return False

    if not check_digit.isdigit():
        return False

    return (
        mrz_check_digit(field)
        == int(check_digit)
    )


def extract_mrz_lines(text: str) -> List[str]:
    lines = []

    for raw_line in (text or "").splitlines():
        line = re.sub(
            r"[^A-Z0-9<]",
            "",
            raw_line.upper(),
        )

        if len(line) >= 40 and "<" in line:
            lines.append(line[:44])

    return lines[-2:]


def parse_passport_mrz(text: str) -> Dict[str, Any]:
    lines = extract_mrz_lines(text)

    if len(lines) < 2:
        return {
            "detected": False,
            "valid": False,
            "status": "NOT_AVAILABLE",
            "lines": [],
        }

    line1 = lines[-2]
    line2 = lines[-1]

    line1 = line1.ljust(44, "<")[:44]
    line2 = line2.ljust(44, "<")[:44]

    validations = {}

    # Passport number: positions 0-8 + check digit 9
    validations["passport_number"] = (
        validate_mrz_field(
            line2[0:9],
            line2[9],
        )
    )

    # Date of birth: 13-18 + check digit 19
    validations["date_of_birth"] = (
        validate_mrz_field(
            line2[13:19],
            line2[19],
        )
    )

    # Expiry: 21-26 + check digit 27
    validations["expiry_date"] = (
        validate_mrz_field(
            line2[21:27],
            line2[27],
        )
    )

    # Personal number: 28-41 + check digit 42
    validations["personal_number"] = (
        validate_mrz_field(
            line2[28:42],
            line2[42],
        )
    )

    # Composite check digit at position 43
    composite_data = (
        line2[0:10]
        + line2[13:20]
        + line2[21:43]
    )

    validations["composite"] = (
        validate_mrz_field(
            composite_data,
            line2[43],
        )
    )

    valid_count = sum(
        validations.values()
    )

    return {
        "detected": True,
        "valid": valid_count >= 4,
        "validation_count": valid_count,
        "validations": validations,
        "lines": lines,
    }


# ============================================================
# DRIVING LICENCE
# ============================================================

def extract_dl_number(text: str) -> Optional[str]:
    patterns = [
        r"\b[A-Z]{2}[- ]?\d{2}[- ]?\d{4,12}\b",
        r"\b[A-Z]{2}\d{2}\d{4,12}\b",
    ]

    upper = (text or "").upper()

    for pattern in patterns:
        match = re.search(pattern, upper)

        if match:
            return re.sub(
                r"[^A-Z0-9]",
                "",
                match.group(0),
            )

    return None


def validate_driving_licence(text: str) -> Dict[str, Any]:
    number = extract_dl_number(text)

    if not number:
        return {
            "number_found": False,
            "format_valid": False,
            "status": "NOT_AVAILABLE",
        }

    format_valid = bool(
        re.fullmatch(
            r"[A-Z]{2}\d{2}\d{4,12}",
            number,
        )
    )

    return {
        "number_found": True,
        "number": number,
        "format_valid": format_valid,
        "status": (
            "STRUCTURALLY_VALID"
            if format_valid
            else "FORMAT_FAILED"
        ),
        "note": (
            "Driving licence authenticity requires "
            "official issuer verification."
        ),
    }


# ============================================================
# VOTER ID / EPIC
# ============================================================

def extract_epic(text: str) -> Optional[str]:
    upper = (text or "").upper()

    patterns = [
        r"\b[A-Z]{3}[0-9]{7}\b",
        r"\b[A-Z]{2,4}[0-9]{6,8}\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, upper)

        if match:
            return match.group(0)

    return None


def validate_voter_id(text: str) -> Dict[str, Any]:
    epic = extract_epic(text)

    if not epic:
        return {
            "number_found": False,
            "format_valid": False,
            "status": "NOT_AVAILABLE",
        }

    format_valid = bool(
        re.fullmatch(
            r"[A-Z]{3}[0-9]{7}",
            epic,
        )
    )

    return {
        "number_found": True,
        "epic": epic,
        "format_valid": format_valid,
        "status": (
            "STRUCTURALLY_VALID"
            if format_valid
            else "FORMAT_FAILED"
        ),
        "note": (
            "EPIC format validation does not "
            "prove electoral-record authenticity."
        ),
    }


# ============================================================
# GSTIN
# ============================================================

GST_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_check_digit(body: str) -> str:
    total = 0

    for index, char in enumerate(body):
        value = GST_CHARS.index(char)
        factor = (index % 2) + 1

        product = value * factor

        total += (
            product // 36
            + product % 36
        )

    remainder = total % 36

    check_value = (
        36 - remainder
    ) % 36

    return GST_CHARS[check_value]


def extract_gstin(text: str) -> Optional[str]:
    upper = (text or "").upper()

    match = re.search(
        r"\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9]Z[A-Z0-9]\b",
        upper,
    )

    return match.group(0) if match else None


def validate_gstin(text: str) -> Dict[str, Any]:
    gstin = extract_gstin(text)

    if not gstin:
        return {
            "number_found": False,
            "format_valid": False,
            "checksum_valid": False,
            "status": "NOT_AVAILABLE",
        }

    state_code = gstin[:2]
    pan = gstin[2:12]
    z_char = gstin[13]

    try:
        state_code_valid = (
            1 <= int(state_code) <= 38
        )
    except ValueError:
        state_code_valid = False

    pan_valid = bool(
        re.fullmatch(
            r"[A-Z]{5}[0-9]{4}[A-Z]",
            pan,
        )
    )

    z_valid = z_char == "Z"

    format_valid = (
        state_code_valid
        and pan_valid
        and z_valid
    )

    checksum_valid = (
        gstin_check_digit(gstin[:14])
        == gstin[14]
    )

    return {
        "number_found": True,
        "gstin": gstin,
        "format_valid": format_valid,
        "checksum_valid": checksum_valid,
        "status": (
            "VALID"
            if format_valid and checksum_valid
            else "CHECKSUM_OR_FORMAT_FAILED"
        ),
    }


# ============================================================
# VISA
# ============================================================

def validate_visa(text: str) -> Dict[str, Any]:
    upper = (text or "").upper()

    visa_detected = "VISA" in upper

    if not visa_detected:
        return {
            "detected": False,
            "status": "NOT_AVAILABLE",
        }

    expiry_match = re.search(
        r"(?:EXPIRY|EXPIRATION|VALID UNTIL|UNTIL)"
        r"\s*[:\-]?\s*"
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        upper,
    )

    return {
        "detected": True,
        "expiry_found": bool(expiry_match),
        "status": "DETECTED",
        "note": (
            "Visa formats and verification mechanisms "
            "vary by issuing country."
        ),
    }


# ============================================================
# CONSISTENCY
# ============================================================

def check_text_consistency(
    document_type: str,
    text: str,
    validation: Dict[str, Any],
) -> Dict[str, Any]:

    mismatches = []

    if document_type == "Aadhaar":
        if validation.get("number_found"):
            if not validation.get("verhoeff_valid"):
                mismatches.append(
                    "Aadhaar checksum failed"
                )

    elif document_type == "PAN":
        if validation.get("number_found"):
            if not validation.get("format_valid"):
                mismatches.append(
                    "PAN format failed"
                )

    elif document_type == "GST":
        if validation.get("number_found"):
            if not validation.get("checksum_valid"):
                mismatches.append(
                    "GSTIN checksum failed"
                )

    elif document_type == "Passport":
        # validation_service.parse_passport_mrz() returns the MRZ
        # result at the top level, not under validation["mrz"].
        # Keep compatibility with an older nested response if present.
        mrz = validation.get("mrz")
        if not isinstance(mrz, dict):
            mrz = validation

        if mrz.get("detected"):
            failed_fields = [
                key
                for key, value
                in mrz.get("validations", {}).items()
                if value is False
            ]

            if failed_fields:
                mismatches.append(
                    "Passport MRZ check digit failure: "
                    + ", ".join(str(field) for field in failed_fields)
                )

            # The validation service also performs technical consistency
            # checks (country/nationality code, sex, and dates).
            consistency_issues = mrz.get(
                "consistency_issues",
                [],
            )

            if isinstance(consistency_issues, list):
                for issue in consistency_issues:
                    issue_text = str(issue).strip()
                    if issue_text and issue_text not in mismatches:
                        mismatches.append(
                            f"Passport consistency issue: {issue_text}"
                        )

    return {
        "consistent": len(mismatches) == 0,
        "mismatches": mismatches,
    }


# ============================================================
# RISK ENGINE
# ============================================================

def calculate_risk(
    document_type: str,
    text: str,
    ocr_confidence: float,
    validation: Dict[str, Any],
    quality: Dict[str, Any],
    forensic: Dict[str, Any],
    magic_valid: bool,
    file_size: int,
) -> Dict[str, Any]:

    score = 0
    signals = []

    # --------------------------------------------------------
    # File integrity
    # --------------------------------------------------------

    if not magic_valid:
        score += 40
        signals.append({
            "signal": "file_signature_mismatch",
            "weight": 40,
            "severity": "HIGH",
        })

    if file_size > MAX_FILE_SIZE:
        score += 30
        signals.append({
            "signal": "file_too_large",
            "weight": 30,
            "severity": "HIGH",
        })

    # --------------------------------------------------------
    # OCR
    # --------------------------------------------------------

    if not text.strip():
        score += 10
        signals.append({
            "signal": "ocr_no_text",
            "weight": 10,
            "severity": "MEDIUM",
        })

    elif ocr_confidence < 35:
        score += 8
        signals.append({
            "signal": "ocr_low_confidence",
            "weight": 8,
            "severity": "MEDIUM",
        })

    elif ocr_confidence < 55:
        score += 3
        signals.append({
            "signal": "ocr_moderate_confidence",
            "weight": 3,
            "severity": "LOW",
        })

    # --------------------------------------------------------
    # Image quality
    # --------------------------------------------------------

    for issue in quality.get("issues", []):
        score += 3

        signals.append({
            "signal": f"image_quality_{issue}",
            "weight": 3,
            "severity": "LOW",
        })

    # --------------------------------------------------------
    # Document-specific validation
    # --------------------------------------------------------

    if document_type == "Aadhaar":
        if validation.get("number_found"):
            if not validation.get("format_valid"):
                score += 20

                signals.append({
                    "signal": "aadhaar_invalid_format",
                    "weight": 20,
                    "severity": "HIGH",
                })

            elif not validation.get("verhoeff_valid"):
                score += 35

                signals.append({
                    "signal": "aadhaar_verhoeff_failed",
                    "weight": 35,
                    "severity": "HIGH",
                })

    elif document_type == "PAN":
        if validation.get("number_found"):
            if not validation.get("format_valid"):
                score += 25

                signals.append({
                    "signal": "pan_format_failed",
                    "weight": 25,
                    "severity": "HIGH",
                })

            if not validation.get(
                "fourth_character_valid"
            ):
                score += 15

                signals.append({
                    "signal": "pan_category_invalid",
                    "weight": 15,
                    "severity": "MEDIUM",
                })

    elif document_type == "Passport":
        mrz = validation.get("mrz", {})

        if mrz.get("detected"):
            failed = [
                key
                for key, value
                in mrz.get("validations", {}).items()
                if value is False
            ]

            if failed:
                score += min(
                    35,
                    len(failed) * 8,
                )

                signals.append({
                    "signal": "passport_mrz_check_failed",
                    "weight": min(
                        35,
                        len(failed) * 8,
                    ),
                    "severity": "HIGH",
                    "fields": failed,
                })

    elif document_type == "Driving Licence":
        if validation.get("number_found"):
            if not validation.get("format_valid"):
                score += 20

                signals.append({
                    "signal": "driving_licence_format_failed",
                    "weight": 20,
                    "severity": "HIGH",
                })

    elif document_type == "Voter ID":
        if validation.get("number_found"):
            if not validation.get("format_valid"):
                score += 20

                signals.append({
                    "signal": "epic_format_failed",
                    "weight": 20,
                    "severity": "HIGH",
                })

    elif document_type == "GST":
        if validation.get("number_found"):
            if not validation.get("format_valid"):
                score += 20

                signals.append({
                    "signal": "gstin_format_failed",
                    "weight": 20,
                    "severity": "HIGH",
                })

            elif not validation.get("checksum_valid"):
                score += 30

                signals.append({
                    "signal": "gstin_checksum_failed",
                    "weight": 30,
                    "severity": "HIGH",
                })

    # --------------------------------------------------------
    # ELA
    # --------------------------------------------------------

    ela = forensic.get("ela", {})

    if ela.get("suspicious"):
        score += 12

        signals.append({
            "signal": "ela_anomaly",
            "weight": 12,
            "severity": "MEDIUM",
        })

    # --------------------------------------------------------
    # Metadata
    # --------------------------------------------------------

    metadata = forensic.get("metadata", {})

    if metadata.get("present"):
        # Metadata existence alone is NOT fraud.
        # We intentionally do not add risk.
        pass

    # --------------------------------------------------------
    # QR
    # --------------------------------------------------------

    qr = forensic.get("qr", {})

    if qr.get("detected") and not qr.get("decoded"):
        score += 2

        signals.append({
            "signal": "qr_detected_but_not_decoded",
            "weight": 2,
            "severity": "LOW",
        })

    # --------------------------------------------------------
    # Unknown document
    # --------------------------------------------------------

    # Unknown is NOT automatically fake.
    if document_type == "Unknown":
        score += 5

        signals.append({
            "signal": "document_type_uncertain",
            "weight": 5,
            "severity": "LOW",
        })

    # --------------------------------------------------------
    # Risk level
    # --------------------------------------------------------

    score = min(score, 100)

    if score <= 20:
        level = "LOW"
    elif score <= 50:
        level = "MEDIUM"
    else:
        level = "HIGH"

    return {
        "score": score,
        "level": level,
        "signals": signals,
        "interpretation": (
            "Risk score represents technical/document "
            "verification signals. It is not a legal "
            "determination of authenticity."
        ),
    }


# ============================================================
# ANALYSIS PIPELINE
# ============================================================

def analyze_document(
    data: bytes,
    filename: str,
    content_type: str,
) -> Dict[str, Any]:

    extension = file_extension(filename)

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file extension.",
        )

    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported content type.",
        )

    if not data:
        raise HTTPException(
            status_code=400,
            detail="Empty file.",
        )

    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="File size exceeds 10 MB limit.",
        )

    magic_valid = validate_magic_bytes(
        data,
        extension,
    )

    if not magic_valid:
        raise HTTPException(
            status_code=400,
            detail="File content does not match its extension.",
        )

    detected_file_type = get_file_type(data)

    # --------------------------------------------------------
    # OCR
    # --------------------------------------------------------

    if detected_file_type == "pdf":
        text, ocr_confidence, image = ocr_pdf(data)

    elif detected_file_type in {"jpeg", "png"}:
        text, ocr_confidence, image = ocr_image(data)

    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file signature.",
        )

    text = normalize_text(text)

    # --------------------------------------------------------
    # Document detection
    # --------------------------------------------------------

    document_type = detect_document_type(text)

    # --------------------------------------------------------
    # Image analysis
    # --------------------------------------------------------

    quality = image_quality(image)

    metadata = extract_metadata(image)

    ela = analyze_ela(image)

    qr = detect_qr(image)

    forensic = {
        "metadata": metadata,
        "ela": ela,
        "qr": qr,
    }

    # --------------------------------------------------------
    # Document-specific validation
    # --------------------------------------------------------

    
    if document_type == "Aadhaar":
        validation = service_validate_aadhaar(text)
    elif document_type == "PAN":
        validation = service_validate_pan(text)
    elif document_type == "Passport":
        validation = service_parse_passport_mrz(text)
    elif document_type == "Driving Licence":
        validation = service_validate_driving_licence(text)
    elif document_type == "Voter ID":
        validation = service_validate_voter_id(text)
    elif document_type == "GST":
        validation = service_validate_gstin(text)
    elif document_type == "Visa":
        validation = service_validate_visa(text)
    else:
        validation = {
           "status": "NOT_AVAILABLE",
    }
    # --------------------------------------------------------
    # Consistency
    # --------------------------------------------------------

    consistency = check_text_consistency(
        document_type,
        text,
        validation,
    )

    # Add consistency signal only when
    # a real mismatch exists.
    if not consistency["consistent"]:
        forensic["consistency"] = consistency
    else:
        forensic["consistency"] = {
            "consistent": True,
            "mismatches": [],
        }

    # --------------------------------------------------------
    # Risk
    # --------------------------------------------------------

    risk = service_calculate_risk(
    document_type=document_type,
    validation=validation,
    forensic=forensic,
    image_quality=quality,
    ocr_confidence=ocr_confidence,
    ocr_text=text,
)

    return {
        "document": {
            "filename": safe_filename(filename),
            "extension": extension,
            "file_type": detected_file_type,
            "size_bytes": len(data),
            "sha256": sha256_bytes(data),
        },

        "document_type": {
            "detected": document_type,
            "supported_types": DOCUMENT_TYPES,
        },

        "ocr": {
            "text": text,
            "text_length": len(text),
            "confidence": ocr_confidence,
        },

        "validation": validation,

        "forensics": forensic,

        "image_quality": quality,

        "consistency": consistency,

        "risk_assessment": risk,

        "technical_disclaimer": (
            "VeriX provides technical verification and "
            "risk signals based on OCR, document structure, "
            "checksum validation and forensic indicators. "
            "These signals do not independently establish "
            "legal authenticity or issuer confirmation."
        ),
    }


# ============================================================
# ROUTES
# ============================================================

@app.get("/")
def root():
    return {
        "service": APP_NAME,
        "version": APP_VERSION,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": APP_NAME,
    }


@app.post("/api/verify")
async def verify_document(
    file: UploadFile = File(...),
):
    data = await file.read()

    filename = safe_filename(
        file.filename or "document"
    )

    content_type = (
        file.content_type
        or "application/octet-stream"
    )

    result = analyze_document(
        data=data,
        filename=filename,
        content_type=content_type,
    )

    return result


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
    )