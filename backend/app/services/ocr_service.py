from typing import Tuple

import pytesseract
from PIL import Image, ImageFilter, ImageOps


TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
MAX_OCR_TEXT = 25000

pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


def normalize_text(text: str) -> str:
    """
    Normalize OCR output while preserving useful document text.
    """
    text = text.replace("\x00", " ")
    text = " ".join(text.split())
    return text.strip()


def preprocess_for_ocr(image: Image.Image) -> Image.Image:
    """
    Prepare image for OCR.
    Keeps the existing VeriX OCR behavior lightweight.
    """
    image = image.convert("RGB")

    gray = ImageOps.grayscale(image)

    # Light contrast enhancement
    gray = ImageOps.autocontrast(gray)

    # Small sharpening improvement
    gray = gray.filter(ImageFilter.SHARPEN)

    return gray


def run_ocr(image: Image.Image) -> Tuple[str, float]:
    """
    Main VeriX OCR pipeline.

    Primary:
        Tesseract PSM 6 + confidence extraction

    Fallback:
        Tesseract PSM 11 when primary OCR returns no text.
    """

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

    # Sparse-text fallback
    if not text.strip():
        text = pytesseract.image_to_string(
            processed,
            config="--oem 3 --psm 11",
        )

    if confidences:
        confidence_score = sum(confidences) / len(confidences)
    else:
        confidence_score = 0.0

    return (
        normalize_text(text)[:MAX_OCR_TEXT],
        round(confidence_score, 2),
    )