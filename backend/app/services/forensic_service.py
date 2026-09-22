import io
import os
from typing import Any, Dict

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageEnhance


def analyze_metadata(
    file_path: str,
    filename: str = "",
) -> Dict[str, Any]:
    """
    Collect basic file metadata and technical signals.
    Metadata alone does not prove a document is fake.
    """

    result: Dict[str, Any] = {
        "available": False,
        "filename": filename or os.path.basename(file_path),
        "extension": os.path.splitext(file_path)[1].lower(),
        "file_size": None,
        "metadata": {},
        "signals": [],
    }

    try:
        if os.path.exists(file_path):
            result["file_size"] = os.path.getsize(file_path)
            result["available"] = True

        try:
            image = Image.open(file_path)
            result["metadata"] = {
                "format": image.format,
                "mode": image.mode,
                "width": image.width,
                "height": image.height,
            }

            if image.info:
                result["metadata"]["embedded_info_keys"] = list(
                    image.info.keys()
                )

        except Exception:
            pass

        return result

    except Exception as exc:
        result["error"] = str(exc)
        return result


def analyze_ela(
    image: Image.Image,
    quality: int = 90,
) -> Dict[str, Any]:
    """
    Error Level Analysis (ELA).

    ELA is a forensic risk signal. It does NOT independently prove
    that an image or document has been tampered with.
    """

    result: Dict[str, Any] = {
        "available": False,
        "detected": False,
        "mean_error": 0.0,
        "max_error": 0.0,
        "threshold": 0.0,
        "status": "NOT_AVAILABLE",
    }

    try:
        original = image.convert("RGB")

        buffer = io.BytesIO()
        original.save(
            buffer,
            format="JPEG",
            quality=quality,
        )
        buffer.seek(0)

        recompressed = Image.open(buffer).convert("RGB")

        diff = ImageChops.difference(
            original,
            recompressed,
        )

        diff_array = np.asarray(diff, dtype=np.float32)

        if diff_array.size == 0:
            return result

        gray_diff = cv2.cvtColor(
            diff_array.astype(np.uint8),
            cv2.COLOR_RGB2GRAY,
        )

        mean_error = float(np.mean(gray_diff))
        max_error = float(np.max(gray_diff))

        threshold = max(18.0, mean_error * 3.0)

        high_error_pixels = np.sum(
            gray_diff > threshold
        )

        total_pixels = gray_diff.size

        high_error_ratio = (
            high_error_pixels / total_pixels
            if total_pixels
            else 0.0
        )

        detected = (
            high_error_ratio > 0.015
            and mean_error > 4.0
        )

        if detected:
            status = "SUSPICIOUS_SIGNAL"
        else:
            status = "NO_STRONG_SIGNAL"

        result.update(
            {
                "available": True,
                "detected": detected,
                "mean_error": round(mean_error, 2),
                "max_error": round(max_error, 2),
                "threshold": round(threshold, 2),
                "high_error_ratio": round(
                    high_error_ratio * 100,
                    2,
                ),
                "status": status,
            }
        )

        return result

    except Exception as exc:
        result["error"] = str(exc)
        return result


def detect_qr(image: Image.Image) -> Dict[str, Any]:
    """
    Detect QR codes using OpenCV.
    """

    result: Dict[str, Any] = {
        "available": False,
        "detected": False,
        "decoded": False,
        "count": 0,
        "data": [],
        "status": "NOT_AVAILABLE",
    }

    try:
        rgb = image.convert("RGB")
        image_array = np.asarray(rgb)

        detector = cv2.QRCodeDetector()

        decoded_data = []

        try:
            multi_result = detector.detectAndDecodeMulti(
                image_array
            )

            if len(multi_result) == 4:
                success, decoded_info, _, _ = multi_result

                if success and decoded_info:
                    for item in decoded_info:
                        if item:
                            decoded_data.append(str(item))

        except Exception:
            pass

        if not decoded_data:
            try:
                data, _, _ = detector.detectAndDecode(
                    image_array
                )

                if data:
                    decoded_data.append(str(data))

            except Exception:
                pass

        detected_points = None

        try:
            detected_points, _ = detector.detect(
                image_array
            )
        except Exception:
            pass

        detected = bool(
            decoded_data
            or detected_points is not None
        )

        result.update(
            {
                "available": True,
                "detected": detected,
                "decoded": bool(decoded_data),
                "count": len(decoded_data),
                "data": decoded_data,
                "status": (
                    "DETECTED_AND_DECODED"
                    if decoded_data
                    else (
                        "DETECTED_NOT_DECODED"
                        if detected
                        else "NOT_DETECTED"
                    )
                ),
            }
        )

        return result

    except Exception as exc:
        result["error"] = str(exc)
        return result


def analyze_image_quality(
    image: Image.Image,
) -> Dict[str, Any]:
    """
    Basic technical image-quality signals.
    """

    result: Dict[str, Any] = {
        "available": False,
        "width": 0,
        "height": 0,
        "blur_score": 0.0,
        "brightness": 0.0,
        "signals": [],
    }

    try:
        rgb = image.convert("RGB")
        array = np.asarray(rgb)

        gray = cv2.cvtColor(
            array,
            cv2.COLOR_RGB2GRAY,
        )

        height, width = gray.shape

        blur_score = float(
            cv2.Laplacian(
                gray,
                cv2.CV_64F,
            ).var()
        )

        brightness = float(np.mean(gray))

        signals = []

        if width < 800 or height < 600:
            signals.append("LOW_RESOLUTION")

        if blur_score < 80:
            signals.append("POSSIBLE_BLUR")

        if brightness < 45:
            signals.append("LOW_BRIGHTNESS")

        if brightness > 235:
            signals.append("HIGH_BRIGHTNESS")

        result.update(
            {
                "available": True,
                "width": width,
                "height": height,
                "blur_score": round(
                    blur_score,
                    2,
                ),
                "brightness": round(
                    brightness,
                    2,
                ),
                "signals": signals,
            }
        )

        return result

    except Exception as exc:
        result["error"] = str(exc)
        return result


def analyze_forensics(
    image: Image.Image,
    file_path: str = "",
    filename: str = "",
) -> Dict[str, Any]:
    """
    Run the complete forensic analysis pipeline.
    """

    ela = analyze_ela(image)
    qr = detect_qr(image)
    quality = analyze_image_quality(image)

    metadata = (
        analyze_metadata(
            file_path,
            filename,
        )
        if file_path
        else {
            "available": False,
            "filename": filename,
            "extension": "",
            "file_size": None,
            "metadata": {},
            "signals": [],
        }
    )

    signals = []

    if ela.get("detected"):
        signals.append("ELA_SUSPICIOUS_SIGNAL")

    if qr.get("detected") and not qr.get("decoded"):
        signals.append("QR_DETECTED_NOT_DECODED")

    signals.extend(
        quality.get("signals", [])
    )

    return {
        "metadata": metadata,
        "ela": ela,
        "qr": qr,
        "image_quality": quality,
        "signals": signals,
        "signal_count": len(signals),
        "technical_assessment": (
            "FORENSIC_SIGNALS_PRESENT"
            if signals
            else "NO_STRONG_FORENSIC_SIGNAL"
        ),
        "disclaimer": (
            "Forensic signals are technical indicators only "
            "and do not independently prove document authenticity "
            "or fraud."
        ),
    }