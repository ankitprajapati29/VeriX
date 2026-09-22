from typing import Any, Dict, List


# Risk thresholds
LOW_MAX = 20
MEDIUM_MAX = 50


def _add_signal(
    signals: List[Dict[str, Any]],
    name: str,
    points: int,
    severity: str,
    reason: str,
) -> None:
    signals.append(
        {
            "signal": name,
            "points": points,
            "severity": severity,
            "reason": reason,
        }
    )


def _get_nested_or_flat(
    data: Dict[str, Any],
    nested_key: str,
) -> Dict[str, Any]:
    """
    Return a document-specific nested validation object when present,
    otherwise use the flat validation object.

    This keeps the Risk Engine compatible with both response shapes
    without requiring changes to main.py.
    """
    nested = data.get(nested_key)

    if isinstance(nested, dict):
        return nested

    return data


def _failed_validation_fields(
    validations: Dict[str, Any],
) -> List[str]:
    """Return validation fields that explicitly failed."""
    if not isinstance(validations, dict):
        return []

    return [
        str(field_name)
        for field_name, field_value in validations.items()
        if field_value is False
    ]


def calculate_risk(
    document_type: str,
    validation: Dict[str, Any] | None = None,
    forensic: Dict[str, Any] | None = None,
    image_quality: Dict[str, Any] | None = None,
    ocr_confidence: float = 0.0,
    ocr_text: str = "",
) -> Dict[str, Any]:
    """
    Calculate explainable technical/document verification risk.

    This is a technical risk assessment based on available signals.
    It does not independently prove authenticity or fraud.
    """

    validation = validation or {}
    forensic = forensic or {}
    image_quality = image_quality or {}

    score = 0
    signals: List[Dict[str, Any]] = []

    # --------------------------------------------------
    # BASIC OCR SIGNALS
    # --------------------------------------------------

    if not ocr_text.strip():
        score += 10
        _add_signal(
            signals,
            "ocr_unavailable",
            10,
            "MEDIUM",
            "No usable OCR text was extracted.",
        )

    elif ocr_confidence < 30:
        score += 8
        _add_signal(
            signals,
            "low_ocr_confidence",
            8,
            "MEDIUM",
            "OCR confidence is low.",
        )

    elif ocr_confidence < 60:
        score += 3
        _add_signal(
            signals,
            "moderate_ocr_confidence",
            3,
            "LOW",
            "OCR confidence is moderate.",
        )

    # --------------------------------------------------
    # DOCUMENT TYPE
    # --------------------------------------------------

    if document_type == "Unknown":
        score += 5
        _add_signal(
            signals,
            "unknown_document_type",
            5,
            "LOW",
            "The document type could not be confidently identified.",
        )

    # --------------------------------------------------
    # VALIDATION SIGNALS
    # --------------------------------------------------

    validation_status = str(
        validation.get("status", "")
    ).upper()

    # --------------------------------------------------
    # AADHAAR
    # --------------------------------------------------

    if document_type == "Aadhaar":
        aadhaar_validation = validation.get(
            "aadhaar",
            validation,
        )

        if aadhaar_validation.get("format_valid") is False:
            score += 20
            _add_signal(
                signals,
                "aadhaar_invalid_format",
                20,
                "HIGH",
                "Aadhaar number format validation failed.",
            )

        if aadhaar_validation.get("verhoeff_valid") is False:
            score += 35
            _add_signal(
                signals,
                "aadhaar_verhoeff_failed",
                35,
                "HIGH",
                "Aadhaar checksum validation failed.",
            )

    # --------------------------------------------------
    # PAN
    # --------------------------------------------------

    if document_type == "PAN":
        # validation_service.validate_pan() returns a flat dictionary.
        # Keep nested compatibility for older response shapes.
        pan_validation = _get_nested_or_flat(
            validation,
            "pan",
        )

        if pan_validation.get("format_valid") is False:
            score += 25
            _add_signal(
                signals,
                "pan_invalid_format",
                25,
                "HIGH",
                "PAN format validation failed.",
            )

        if pan_validation.get("fourth_character_valid") is False:
            score += 15
            _add_signal(
                signals,
                "pan_invalid_category",
                15,
                "MEDIUM",
                "PAN category validation failed.",
            )

        # Consume the enhanced validation fields returned by
        # validation_service.py. These are technical consistency signals,
        # not proof of legal authenticity.
        pan_consistency_issues = pan_validation.get(
            "consistency_issues",
            [],
        )

        if isinstance(pan_consistency_issues, list) and pan_consistency_issues:
            mismatch_text = ", ".join(
                str(item) for item in pan_consistency_issues
            )
            score += 10
            _add_signal(
                signals,
                "pan_consistency_issue",
                10,
                "MEDIUM",
                "PAN technical consistency check reported an issue"
                + (f": {mismatch_text}." if mismatch_text else "."),
            )

    # --------------------------------------------------
    # PASSPORT / MRZ
    # --------------------------------------------------

    if document_type == "Passport":
        # validation_service.parse_passport_mrz() returns a flat dictionary.
        # Keep nested compatibility for older response shapes.
        passport_validation = _get_nested_or_flat(
            validation,
            "passport",
        )

        if passport_validation.get("detected") is True:
            mrz_valid = passport_validation.get("valid")
            validations = passport_validation.get("validations", {})

            failed_fields = _failed_validation_fields(validations)

            if mrz_valid is False:
                failed_count = len(failed_fields)
                passport_points = min(35, max(8, failed_count * 8))

                score += passport_points

                if failed_fields:
                    failed_text = ", ".join(failed_fields)
                    reason = (
                        "Passport ICAO MRZ check-digit validation "
                        f"failed for: {failed_text}."
                    )
                else:
                    reason = "Passport ICAO MRZ validation failed."

                _add_signal(
                    signals,
                    "passport_mrz_failed",
                    passport_points,
                    "HIGH",
                    reason,
                )

            passport_consistency_issues = passport_validation.get(
                "consistency_issues",
                [],
            )

            if (
                isinstance(passport_consistency_issues, list)
                and passport_consistency_issues
            ):
                mismatch_text = ", ".join(
                    str(item) for item in passport_consistency_issues
                )
                score += 10
                _add_signal(
                    signals,
                    "passport_consistency_issue",
                    10,
                    "MEDIUM",
                    "Passport technical consistency check reported an issue"
                    + (f": {mismatch_text}." if mismatch_text else "."),
                )

            if passport_validation.get("authenticity_status") == "EXPIRED_DOCUMENT":
                score += 20
                _add_signal(
                    signals,
                    "passport_expired",
                    20,
                    "HIGH",
                    "Passport MRZ expiry date indicates that the document is expired.",
                )

    # --------------------------------------------------
    # DRIVING LICENCE
    # --------------------------------------------------

    if document_type == "Driving Licence":
        # validation_service.validate_driving_licence() returns a flat dictionary.
        # Keep nested compatibility for older response shapes.
        dl_validation = _get_nested_or_flat(
            validation,
            "driving_licence",
        )

        if dl_validation.get("format_valid") is False:
            score += 20
            _add_signal(
                signals,
                "driving_licence_invalid_format",
                20,
                "HIGH",
                "Driving licence number format validation failed.",
            )

        # The enhanced validation service already checks expiry and date
        # ordering. The risk engine must consume those results.
        if dl_validation.get("is_expired") is True:
            score += 25
            _add_signal(
                signals,
                "driving_licence_expired",
                25,
                "HIGH",
                "Driving licence expiry date indicates that the document is expired.",
            )

        dl_date_issues = dl_validation.get("date_issues", [])
        if isinstance(dl_date_issues, list):
            non_expiry_date_issues = [
                str(issue)
                for issue in dl_date_issues
                if str(issue).lower().strip() != "licence appears expired"
            ]

            if non_expiry_date_issues:
                mismatch_text = ", ".join(non_expiry_date_issues)
                score += 10
                _add_signal(
                    signals,
                    "driving_licence_date_issue",
                    10,
                    "MEDIUM",
                    "Driving licence date consistency check reported an issue"
                    + (f": {mismatch_text}." if mismatch_text else "."),
                )

        dl_consistency_issues = dl_validation.get(
            "consistency_issues",
            [],
        )

        if isinstance(dl_consistency_issues, list):
            non_date_consistency_issues = [
                str(issue)
                for issue in dl_consistency_issues
                if str(issue) not in {
                    str(item) for item in dl_date_issues
                }
            ]

            if non_date_consistency_issues:
                mismatch_text = ", ".join(non_date_consistency_issues)
                score += 10
                _add_signal(
                    signals,
                    "driving_licence_consistency_issue",
                    10,
                    "MEDIUM",
                    "Driving licence technical consistency check reported an issue"
                    + (f": {mismatch_text}." if mismatch_text else "."),
                )

    # --------------------------------------------------
    # VOTER ID
    # --------------------------------------------------

    if document_type == "Voter ID":
        voter_validation = validation.get(
            "voter_id",
            validation,
        )

        if voter_validation.get("format_valid") is False:
            score += 20
            _add_signal(
                signals,
                "voter_id_invalid_format",
                20,
                "HIGH",
                "Voter ID format validation failed.",
            )

    # --------------------------------------------------
    # GST
    # --------------------------------------------------

    if document_type == "GST":
        gst_validation = validation.get(
            "gst",
            validation,
        )

        if gst_validation.get("format_valid") is False:
            score += 20
            _add_signal(
                signals,
                "gst_invalid_format",
                20,
                "HIGH",
                "GSTIN format validation failed.",
            )

        if gst_validation.get("checksum_valid") is False:
            score += 30
            _add_signal(
                signals,
                "gst_checksum_failed",
                30,
                "HIGH",
                "GSTIN checksum validation failed.",
            )

    # --------------------------------------------------
    # IMAGE QUALITY
    # --------------------------------------------------

    quality_issues = image_quality.get(
        "issues",
        [],
    )

    if isinstance(quality_issues, list):
        for issue in quality_issues:
            issue_name = str(issue).lower().strip()

            if issue_name == "low_resolution":
                score += 3
                _add_signal(
                    signals,
                    "image_quality_low_resolution",
                    3,
                    "LOW",
                    "Image resolution is low.",
                )

            elif issue_name == "blur_detected":
                score += 3
                _add_signal(
                    signals,
                    "image_quality_blur_detected",
                    3,
                    "LOW",
                    "Possible image blur was detected.",
                )

            elif issue_name == "too_dark":
                score += 3
                _add_signal(
                    signals,
                    "image_quality_too_dark",
                    3,
                    "LOW",
                    "Image brightness is too low.",
                )

            elif issue_name == "overexposed":
                score += 3
                _add_signal(
                    signals,
                    "image_quality_overexposed",
                    3,
                    "LOW",
                    "Image brightness is unusually high.",
                )

    # --------------------------------------------------
    # FORENSIC SIGNALS
    # --------------------------------------------------

    ela = forensic.get(
        "ela",
        {},
    )

    qr = forensic.get(
        "qr",
        {},
    )

    if ela.get("suspicious") is True:
        score += 12
        _add_signal(
            signals,
            "ela_suspicious_signal",
            12,
            "MEDIUM",
            "ELA analysis detected a suspicious technical signal.",
        )

    if (
        qr.get("detected") is True
        and qr.get("decoded") is False
    ):
        score += 2
        _add_signal(
            signals,
            "qr_detected_not_decoded",
            2,
            "LOW",
            "A QR-like pattern was detected but could not be decoded.",
        )

    # --------------------------------------------------
    # DOCUMENT CONSISTENCY
    # --------------------------------------------------
    # main.py provides:
    # {
    #     "consistent": True/False,
    #     "mismatches": [...]
    # }
    #
    # This is a technical consistency signal only.
    # It does not independently prove fraud.

    consistency = forensic.get(
        "consistency",
        {},
    )

    if consistency.get("consistent") is False:
        mismatches = consistency.get(
            "mismatches",
            [],
        )

        if isinstance(mismatches, list):
            mismatch_text = ", ".join(
                str(item)
                for item in mismatches
            )
        else:
            mismatch_text = str(mismatches)

        consistency_points = 10
        score += consistency_points

        _add_signal(
            signals,
            "document_consistency_mismatch",
            consistency_points,
            "MEDIUM",
            (
                "Document consistency checks reported "
                "a technical mismatch"
                + (
                    f": {mismatch_text}."
                    if mismatch_text
                    else "."
                )
            ),
        )

    # --------------------------------------------------
    # UNKNOWN DOCUMENT
    # --------------------------------------------------
    # Unknown documents do not receive a numeric risk score.
    # Document-specific validation could not be reliably performed.

    if document_type == "Unknown":
        severity_order = {
            "HIGH": 3,
            "MEDIUM": 2,
            "LOW": 1,
        }

        highest_severity = "LOW"
        if signals:
            highest_severity = max(
                signals,
                key=lambda item: severity_order.get(
                    item.get("severity", "LOW"),
                    1,
                ),
            ).get("severity", "LOW")

        return {
            "score": None,
            "level": "UNAVAILABLE",
            "signals": signals,
            "signal_count": len(signals),
            "highest_signal_severity": highest_severity,
            "technical_assessment": "INSUFFICIENT_EVIDENCE",
            "disclaimer": (
                "Document type could not be confidently identified. "
                "A numeric risk score is therefore unavailable. "
                "This does not confirm authenticity or fraud."
            ),
        }

    # --------------------------------------------------
    # SCORE CAP
    # --------------------------------------------------

    score = min(score, 100)

    # --------------------------------------------------
    # RISK LEVEL
    # --------------------------------------------------

    if score <= LOW_MAX:
        level = "LOW"

    elif score <= MEDIUM_MAX:
        level = "MEDIUM"

    else:
        level = "HIGH"

    # --------------------------------------------------
    # HIGHEST SIGNAL SEVERITY
    # --------------------------------------------------

    severity_order = {
        "HIGH": 3,
        "MEDIUM": 2,
        "LOW": 1,
    }

    highest_severity = "LOW"

    if signals:
        highest_severity = max(
            signals,
            key=lambda item: severity_order.get(
                item.get("severity", "LOW"),
                1,
            ),
        ).get(
            "severity",
            "LOW",
        )

    # --------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------

    return {
        "score": score,
        "level": level,
        "signals": signals,
        "signal_count": len(signals),
        "highest_signal_severity": highest_severity,
        "technical_assessment": (
            "HIGH_TECHNICAL_RISK"
            if level == "HIGH"
            else (
                "MEDIUM_TECHNICAL_RISK"
                if level == "MEDIUM"
                else "LOW_TECHNICAL_RISK"
            )
        ),
        "disclaimer": (
            "Risk score represents technical/document verification "
            "signals. It is not a legal determination of authenticity "
            "or fraud."
        ),
    }