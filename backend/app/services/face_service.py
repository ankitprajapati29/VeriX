from typing import Any, Dict, List, Tuple

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter


# ============================================================
# FACE DETECTION CONFIGURATION
# ============================================================

CASCADE_PATH = (
    cv2.data.haarcascades
    + "haarcascade_frontalface_default.xml"
)

CASCADE = cv2.CascadeClassifier(CASCADE_PATH)


# Multiple detection configurations.
# Lower minNeighbors = better recall for small/low-quality faces.
# Higher minNeighbors = fewer false positives.
DETECTION_CONFIGS = [
    {
        "scale_factor": 1.08,
        "min_neighbors": 7,
        "min_size": (28, 28),
    },
    {
        "scale_factor": 1.10,
        "min_neighbors": 8,
        "min_size": (32, 32),
    },
    {
        "scale_factor": 1.12,
        "min_neighbors": 9,
        "min_size": (36, 36),
    },
]


# ============================================================
# IMAGE PREPROCESSING
# ============================================================

def _prepare_variants(image: Image.Image) -> List[np.ndarray]:
    """
    Create multiple grayscale image variants.

    This helps with:
    - small ID-card photos
    - low contrast scans
    - slightly blurry documents
    - uneven brightness
    """

    rgb = image.convert("RGB")

    # Original RGB -> grayscale
    original = np.asarray(
        rgb,
        dtype=np.uint8,
    )

    original = np.ascontiguousarray(original)

    gray = cv2.cvtColor(
        original,
        cv2.COLOR_RGB2GRAY,
    )

    variants = []

    # --------------------------------------------------------
    # 1. Original grayscale
    # --------------------------------------------------------
    variants.append(gray)

    # --------------------------------------------------------
    # 2. Histogram equalization
    # --------------------------------------------------------
    equalized = cv2.equalizeHist(gray)

    variants.append(equalized)

    # --------------------------------------------------------
    # 3. CLAHE
    # Better for uneven lighting than global equalization.
    # --------------------------------------------------------
    clahe = cv2.createCLAHE(
        clipLimit=2.0,
        tileGridSize=(8, 8),
    )

    clahe_gray = clahe.apply(gray)

    variants.append(clahe_gray)

    # --------------------------------------------------------
    # 4. Light sharpening
    # --------------------------------------------------------
    sharpened = cv2.GaussianBlur(
        gray,
        (0, 0),
        1.0,
    )

    sharpened = cv2.addWeighted(
        gray,
        1.5,
        sharpened,
        -0.5,
        0,
    )

    variants.append(sharpened)

    # --------------------------------------------------------
    # 5. Mild denoising + CLAHE
    # --------------------------------------------------------
    denoised = cv2.GaussianBlur(
        gray,
        (3, 3),
        0,
    )

    denoised = clahe.apply(denoised)

    variants.append(denoised)

    return variants


# ============================================================
# UPSCALING
# ============================================================

def _upscale_if_needed(
    gray: np.ndarray,
) -> np.ndarray:
    """
    Upscale smaller document images so that small ID-photo
    faces become easier for Haar Cascade to detect.
    """

    height, width = gray.shape[:2]

    # Do not unnecessarily enlarge already-large images.
    if width >= 1400 or height >= 1400:
        return gray

    scale = 2.0

    upscaled = cv2.resize(
        gray,
        None,
        fx=scale,
        fy=scale,
        interpolation=cv2.INTER_CUBIC,
    )

    return upscaled


# ============================================================
# DETECTION
# ============================================================

def _detect_on_image(
    gray: np.ndarray,
) -> List[Tuple[int, int, int, int]]:
    """
    Run several Haar Cascade configurations on one image.
    """

    detected = []

    for config in DETECTION_CONFIGS:

        try:
            faces = CASCADE.detectMultiScale(
                gray,
                scaleFactor=config["scale_factor"],
                minNeighbors=config["min_neighbors"],
                minSize=config["min_size"],
            )

            for (
                x,
                y,
                width,
                height,
            ) in faces:

                detected.append(
                    (
                        int(x),
                        int(y),
                        int(width),
                        int(height),
                    )
                )

        except Exception:
            # Continue with the remaining detector passes.
            continue

    return detected


# ============================================================
# IOU / DUPLICATE MERGING
# ============================================================

def _iou(
    box_a: Tuple[int, int, int, int],
    box_b: Tuple[int, int, int, int],
) -> float:
    """
    Calculate Intersection over Union between two face boxes.
    """

    ax, ay, aw, ah = box_a
    bx, by, bw, bh = box_b

    a_x2 = ax + aw
    a_y2 = ay + ah

    b_x2 = bx + bw
    b_y2 = by + bh

    intersection_x1 = max(ax, bx)
    intersection_y1 = max(ay, by)

    intersection_x2 = min(
        a_x2,
        b_x2,
    )

    intersection_y2 = min(
        a_y2,
        b_y2,
    )

    intersection_width = max(
        0,
        intersection_x2 - intersection_x1,
    )

    intersection_height = max(
        0,
        intersection_y2 - intersection_y1,
    )

    intersection_area = (
        intersection_width
        * intersection_height
    )

    area_a = aw * ah
    area_b = bw * bh

    union_area = (
        area_a
        + area_b
        - intersection_area
    )

    if union_area <= 0:
        return 0.0

    return intersection_area / union_area


def _merge_duplicate_faces(
    faces: List[Tuple[int, int, int, int]],
) -> List[Tuple[int, int, int, int]]:
    """
    Keep only face regions supported by multiple independent
    detector passes.

    A single Haar detection is not enough because document text,
    QR-like patterns, logos, and portrait artifacts can trigger
    false positives.
    """

    if not faces:
        return []

    # Sort largest first so a representative box can be retained.
    faces = sorted(
        faces,
        key=lambda box: box[2] * box[3],
        reverse=True,
    )

    clusters: List[List[Tuple[int, int, int, int]]] = []

    for candidate in faces:
        placed = False

        for cluster in clusters:
            # Compare against the strongest representative in cluster.
            overlap = max(
                _iou(candidate, existing)
                for existing in cluster
            )

            if overlap >= 0.35:
                cluster.append(candidate)
                placed = True
                break

        if not placed:
            clusters.append([candidate])

    confirmed = []

    for cluster in clusters:
        # Require repeated support from multiple detector passes.
        if len(cluster) < 2:
            continue

        # Use the largest supported detection as the final box.
        representative = max(
            cluster,
            key=lambda box: box[2] * box[3],
        )
        confirmed.append(representative)

    return confirmed


# ============================================================
# FACE QUALITY FILTER
# ============================================================

def _filter_face_boxes(
    faces: List[Tuple[int, int, int, int]],
    image_width: int,
    image_height: int,
) -> List[Tuple[int, int, int, int]]:
    """
    Remove detections that are unlikely to be a real face.

    The detector is intentionally conservative for identity
    documents because false face boxes are worse than missing a
    very small portrait.
    """

    filtered = []

    image_area = image_width * image_height
    min_dimension = min(image_width, image_height)

    for x, y, width, height in faces:
        if width <= 0 or height <= 0:
            continue

        # Minimum absolute size.
        if width < 28 or height < 28:
            continue

        # A detected face should occupy a meaningful region.
        if min(width, height) < min_dimension * 0.035:
            continue

        face_area = width * height

        # Reject extremely tiny or almost full-image regions.
        if face_area < image_area * 0.0015:
            continue

        if face_area > image_area * 0.35:
            continue

        # Human face boxes are normally close to square.
        ratio = width / max(height, 1)

        if ratio < 0.55 or ratio > 1.55:
            continue

        # Clamp coordinates to image bounds.
        x = max(0, min(x, image_width - 1))
        y = max(0, min(y, image_height - 1))

        width = min(width, image_width - x)
        height = min(height, image_height - y)

        if width < 28 or height < 28:
            continue

        filtered.append(
            (
                int(x),
                int(y),
                int(width),
                int(height),
            )
        )

    return filtered


# ============================================================
# MAIN FACE DETECTION
# ============================================================

def detect_faces(
    image: Image.Image,
) -> Dict[str, Any]:
    """
    Conservative human-face detection for identity documents.

    A face is reported only when the same region is supported by
    multiple detector passes. This reduces false positives from
    document text, symbols, QR patterns, and portrait-like artifacts.

    This is a technical image-analysis signal only. It does not
    prove identity or document authenticity.
    """

    try:
        if image is None:
            return {
                "available": False,
                "detected": False,
                "count": 0,
                "status": "INVALID_IMAGE",
                "faces": [],
                "error": "No image was supplied.",
            }

        if CASCADE.empty():
            return {
                "available": False,
                "detected": False,
                "count": 0,
                "status": "MODEL_LOAD_ERROR",
                "faces": [],
                "error": "OpenCV Haar Cascade could not be loaded.",
            }

        rgb_image = image.convert("RGB")
        width, height = rgb_image.size

        if width <= 0 or height <= 0:
            return {
                "available": False,
                "detected": False,
                "count": 0,
                "status": "INVALID_IMAGE",
                "faces": [],
                "error": "Image dimensions are invalid.",
            }

        variants = _prepare_variants(rgb_image)

        all_faces = []

        # Every variant is treated as an independent support pass.
        for variant in variants:
            faces = _detect_on_image(variant)
            faces = _filter_face_boxes(
                faces,
                variant.shape[1],
                variant.shape[0],
            )

            for face in faces:
                all_faces.append(face)

            upscaled = _upscale_if_needed(variant)

            if (
                upscaled.shape[0] != variant.shape[0]
                or upscaled.shape[1] != variant.shape[1]
            ):
                upscaled_faces = _detect_on_image(upscaled)

                scale_x = variant.shape[1] / upscaled.shape[1]
                scale_y = variant.shape[0] / upscaled.shape[0]

                for x, y, face_width, face_height in upscaled_faces:
                    converted = (
                        int(x * scale_x),
                        int(y * scale_y),
                        int(face_width * scale_x),
                        int(face_height * scale_y),
                    )

                    converted_faces = _filter_face_boxes(
                        [converted],
                        variant.shape[1],
                        variant.shape[0],
                    )

                    all_faces.extend(converted_faces)

        # Final filtering in original image coordinates.
        all_faces = _filter_face_boxes(
            all_faces,
            width,
            height,
        )

        final_faces = _merge_duplicate_faces(all_faces)

        face_list = [
            {
                "x": int(x),
                "y": int(y),
                "width": int(face_width),
                "height": int(face_height),
            }
            for x, y, face_width, face_height in final_faces
        ]

        face_count = len(face_list)

        if face_count == 0:
            status = "NO_FACE_DETECTED"
            description = (
                "No face was detected with sufficient multi-pass support."
            )
        elif face_count == 1:
            status = "ONE_FACE_DETECTED"
            description = (
                "One face was detected with repeated multi-pass support."
            )
        else:
            status = "MULTIPLE_FACES_DETECTED"
            description = (
                f"{face_count} faces were detected with repeated "
                "multi-pass support."
            )

        return {
            "available": True,
            "detected": face_count > 0,
            "count": face_count,
            "status": status,
            "faces": face_list,
            "passes": len(variants),
            "method": (
                "OpenCV Haar Cascade "
                "conservative multi-pass detection"
            ),
            "note": (
                "Face detection is a technical image-analysis signal. "
                "It does not prove identity or document authenticity."
            ),
        }

    except Exception as exc:
        return {
            "available": False,
            "detected": False,
            "count": 0,
            "status": "ANALYSIS_FAILED",
            "faces": [],
            "error": str(exc),
        }