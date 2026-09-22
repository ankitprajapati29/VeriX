import re
from typing import Any, Dict, List, Optional
from datetime import datetime


# ============================================================
# COMMON HELPERS
# ============================================================

def digits_only(value: str) -> str:
    return re.sub(r"\D", "", value or "")


# ============================================================
# AADHAAR / VERHOEFF (UNCHANGED - PRESERVED EXACTLY)
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


def validate_verhoeff(number: str) -> bool:
    number = digits_only(number)

    if len(number) != 12:
        return False

    checksum = 0

    for index, digit in enumerate(reversed(number)):
        checksum = VERHOEFF_D[checksum][
            VERHOEFF_P[index % 8][int(digit)]
        ]

    return checksum == 0


def extract_aadhaar_number(text: str) -> Optional[str]:
    """
    Extract an Aadhaar number from OCR text using multiple conservative
    patterns. The function prefers candidates that pass Verhoeff so that
    OCR noise is less likely to be treated as a valid Aadhaar number.
    """

    raw_text = text or ""
    if not raw_text.strip():
        return None

    # OCR can introduce common separators or line-break variations.
    normalized = raw_text.upper().replace("\u00a0", " ")

    candidates: List[str] = []

    def add_candidate(value: str) -> None:
        number = digits_only(value)
        if len(number) == 12 and number not in candidates:
            candidates.append(number)

    # 1. Standard Aadhaar grouping: 4 4 4.
    grouped_patterns = [
        r"(?<!\d)(\d{4})[\s\-./]*(\d{4})[\s\-./]*(\d{4})(?!\d)",
        r"(?<!\d)(\d{4})\s+(\d{4})\s+(\d{4})(?!\d)",
    ]

    for pattern in grouped_patterns:
        for match in re.finditer(pattern, normalized):
            add_candidate("".join(match.groups()))

    # 2. Continuous 12-digit OCR output.
    for match in re.finditer(r"(?<!\d)(\d{12})(?!\d)", normalized):
        add_candidate(match.group(1))

    # 3. Handle common OCR substitutions only when the whole candidate
    # is already shaped like a 12-digit number.
    ocr_digit_map = str.maketrans({
        "O": "0",
        "Q": "0",
        "I": "1",
        "L": "1",
        "Z": "2",
        "S": "5",
        "G": "6",
        "B": "8",
    })

    for raw_line in normalized.splitlines():
        compact = re.sub(r"[^0-9OQILZSGB]", "", raw_line)
        if len(compact) == 12:
            corrected = compact.translate(ocr_digit_map)
            add_candidate(corrected)

    # 4. If OCR split the number into separate 4-digit chunks, recover
    # the chunks from the same line while keeping the pattern conservative.
    for raw_line in normalized.splitlines():
        chunks = re.findall(r"(?<!\d)\d{4}(?!\d)", raw_line)
        if len(chunks) >= 3:
            for index in range(len(chunks) - 2):
                add_candidate("".join(chunks[index:index + 3]))

    # Prefer a candidate that independently passes Verhoeff.
    valid_candidates = [
        candidate
        for candidate in candidates
        if validate_verhoeff(candidate)
    ]

    if len(valid_candidates) == 1:
        return valid_candidates[0]

    # If there is no unique checksum-valid candidate, only return an
    # exact OCR candidate. Do not invent/correct a number from weak evidence.
    if candidates:
        return candidates[0]

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
        "masked_number": "XXXX XXXX " + number[-4:],
        "format_valid": format_valid,
        "verhoeff_valid": verhoeff_valid,
        "status": (
            "VALID"
            if verhoeff_valid
            else "CHECKSUM_FAILED"
        ),
    }


# ============================================================
# PAN (IMPROVED VALIDATION)
# ============================================================

PAN_REGEX = re.compile(r"[A-Z]{5}[0-9]{4}[A-Z]")

PAN_FOURTH_CHARACTER_TYPES = {
    "P": "Individual",
    "C": "Company",
    "H": "Hindu Undivided Family",
    "A": "Association of Persons",
    "B": "Body of Individuals",
    "G": "Government Agency",
    "J": "Artificial Juridical Person",
    "L": "Local Authority",
    "F": "Firm / Partnership / LLP",
    "T": "Trust",
}


def _normalize_pan_candidate(value: str) -> Optional[str]:
    """Normalize a PAN-like OCR candidate conservatively."""
    raw = re.sub(r"[^A-Z0-9]", "", (value or "").upper())

    if len(raw) != 10:
        return None

    chars = list(raw)

    # PAN structure: 5 letters + 4 digits + 1 letter
    # Positions that should be letters: 0, 1, 2, 3, 4, 9
    for index in [0, 1, 2, 3, 4, 9]:
        if chars[index].isdigit():
            # Conservative OCR correction for letter positions
            ocr_letter_map = {
                "0": "O",
                "1": "I",
                "2": "Z",
                "5": "S",
                "6": "G",
                "8": "B",
            }
            chars[index] = ocr_letter_map.get(chars[index], chars[index])

    # Positions that should be digits: 5, 6, 7, 8
    for index in [5, 6, 7, 8]:
        if chars[index].isalpha():
            # Conservative OCR correction for digit positions
            ocr_digit_map = {
                "O": "0",
                "Q": "0",
                "D": "0",
                "I": "1",
                "L": "1",
                "Z": "2",
                "S": "5",
                "G": "6",
                "B": "8",
            }
            chars[index] = ocr_digit_map.get(chars[index], chars[index])

    candidate = "".join(chars)

    # Verify final structure matches PAN pattern
    return candidate if PAN_REGEX.fullmatch(candidate) else None


def extract_pan(text: str) -> Optional[str]:
    """Extract PAN from OCR text with separator/OCR-noise tolerance."""
    upper = (text or "").upper()
    if not upper.strip():
        return None

    candidates = []

    # Pattern 1: Exact standard PAN
    for match in PAN_REGEX.finditer(upper):
        pan = match.group(0)
        if pan not in candidates:
            candidates.append(pan)

    # Pattern 2: PAN with spaces, hyphens, dots (OCR artifacts)
    # Example: "ABCDE 1234 F" or "ABCDE-1234-F"
    token_pattern = re.compile(
        r"(?<![A-Z0-9])"
        r"([A-Z0-9](?:[\s\-./]*[A-Z0-9]){9})"
        r"(?![A-Z0-9])"
    )

    for match in token_pattern.finditer(upper):
        candidate = _normalize_pan_candidate(match.group(1))
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    # Pattern 3: Line-level extraction with unusual separators
    for line in upper.splitlines():
        compact = re.sub(r"[^A-Z0-9]", "", line)
        if len(compact) == 10:
            candidate = _normalize_pan_candidate(compact)
            if candidate and candidate not in candidates:
                candidates.append(candidate)

    # Prioritize candidates with valid 4th character
    for candidate in candidates:
        if candidate[3] in PAN_FOURTH_CHARACTER_TYPES:
            return candidate

    # Return first valid candidate if no recognized entity type found
    return candidates[0] if candidates else None


def validate_pan(text: str) -> Dict[str, Any]:
    """
    Validate PAN using structural rules and 4th character entity type.
    
    Note: PAN does NOT have a public checksum algorithm like Aadhaar Verhoeff.
    This validation is structural only.
    """
    pan = extract_pan(text)

    if not pan:
        return {
            "number_found": False,
            "format_valid": False,
            "fourth_character_valid": False,
            "entity_type": None,
            "status": "NOT_AVAILABLE",
            "official_verification": "NOT_PERFORMED",
        }

    format_valid = bool(PAN_REGEX.fullmatch(pan))
    fourth_character = pan[3]
    fourth_character_valid = fourth_character in PAN_FOURTH_CHARACTER_TYPES
    entity_type = PAN_FOURTH_CHARACTER_TYPES.get(fourth_character, "Unknown")

    # Extract name and DOB if present in OCR (optional enhancement)
    name_match = re.search(
        r"(?:NAME|Name)\s*[:\-]?\s*([A-Z\s]{3,50})",
        text,
        re.IGNORECASE
    )
    extracted_name = name_match.group(1).strip() if name_match else None

    dob_match = re.search(
        r"(?:DATE OF BIRTH|DOB|Birth)\s*[:\-]?\s*(\d{2}[/-]\d{2}[/-]\d{4})",
        text,
        re.IGNORECASE
    )
    extracted_dob = dob_match.group(1) if dob_match else None

    # Consistency signals: these are technical indicators only.
    consistency_issues: List[str] = []

    if format_valid and not fourth_character_valid:
        consistency_issues.append("PAN entity category is not recognized.")

    if extracted_dob:
        try:
            parsed_dob = datetime.strptime(
                extracted_dob.replace("-", "/"),
                "%d/%m/%Y",
            ).date()
            if parsed_dob > datetime.now().date():
                consistency_issues.append("Date of birth is in the future.")
        except ValueError:
            consistency_issues.append("Date of birth has an invalid date value.")

    return {
        "number_found": True,
        "masked_pan": pan[:3] + "XXXXX" + pan[-1],
        "format_valid": format_valid,
        "fourth_character": fourth_character,
        "fourth_character_valid": fourth_character_valid,
        "entity_type": entity_type,
        "extracted_name": extracted_name,
        "extracted_dob": extracted_dob,
        "consistency_valid": len(consistency_issues) == 0,
        "consistency_issues": consistency_issues,
        "status": (
            "VALID"
            if format_valid and fourth_character_valid and not consistency_issues
            else "REVIEW_REQUIRED"
            if format_valid
            else "FORMAT_FAILED"
        ),
        "official_verification": "NOT_PERFORMED",
        "authenticity_status": (
            "TECHNICAL_CHECKS_PASSED"
            if format_valid and fourth_character_valid and not consistency_issues
            else "SUSPICIOUS_TECHNICAL_SIGNAL"
        ),
        "note": (
            "PAN structure, entity category and available field consistency "
            "were checked locally. These checks do not prove legal authenticity. "
            "Official Income Tax Department verification is required for authenticity."
        ),
    }


# ============================================================
# PASSPORT / ICAO MRZ (IMPROVED VALIDATION)
# ============================================================

ICAO_WEIGHTS = [7, 3, 1]


def mrz_char_value(char: str) -> int:
    """Convert MRZ character to numeric value per ICAO 9303"""
    if char == "<":
        return 0
    if char.isdigit():
        return int(char)
    if "A" <= char <= "Z":
        return ord(char) - ord("A") + 10
    return 0


def icao_check_digit(data: str) -> int:
    """Calculate ICAO MRZ check digit using 7-3-1 weighting"""
    total = 0
    for index, char in enumerate(data):
        value = mrz_char_value(char)
        weight = ICAO_WEIGHTS[index % 3]
        total += value * weight
    return total % 10


def validate_mrz_check_digit(field: str, check_digit_char: str) -> bool:
    """Validate a single MRZ field check digit"""
    if len(check_digit_char) != 1 or not check_digit_char.isdigit():
        return False
    
    expected = icao_check_digit(field)
    actual = int(check_digit_char)
    
    return expected == actual


def _normalize_mrz_line(raw_line: str) -> str:
    """Normalize MRZ line from OCR text"""
    line = (raw_line or "").upper().strip()
    
    # Remove non-MRZ characters
    line = re.sub(r"[^A-Z0-9<]", "", line)
    
    # Handle common OCR substitutions for filler character
    line = line.replace("«", "<").replace("‹", "<").replace(">", "<")
    line = line.replace("‹", "<").replace("›", "<")
    
    return line


def extract_mrz_lines(text: str) -> List[str]:
    """
    Extract TD3 passport MRZ lines (two 44-character lines).
    Handles OCR noise and finds the strongest MRZ candidate pair.
    """
    normalized_lines = [
        _normalize_mrz_line(line)
        for line in (text or "").splitlines()
    ]
    
    # Filter out empty lines
    normalized_lines = [line for line in normalized_lines if line]
    
    # Find MRZ-like lines (40-45 characters, contains <, may start with P)
    candidates = []
    
    for index, line in enumerate(normalized_lines):
        score = 0
        
        # Length check (TD3 MRZ = 44 chars, allow slight variation)
        if 40 <= len(line) <= 45:
            score += 3
        
        # Contains filler characters (strong MRZ indicator)
        if "<" in line:
            score += 3
        
        # First line typically starts with P< (passport type code)
        if line.startswith(("P<", "P0", "PO", "PC", "PD")):
            score += 4
        
        # Store candidates with sufficient score
        if score >= 3:
            candidates.append((index, score, line))
    
    # Find consecutive line pairs (MRZ lines are adjacent)
    pairs = []
    for i in range(len(candidates) - 1):
        first_index, first_score, first_line = candidates[i]
        second_index, second_score, second_line = candidates[i + 1]
        
        # Lines should be adjacent (within 2 positions for OCR noise tolerance)
        if second_index - first_index <= 2:
            combined_score = first_score + second_score
            pairs.append((combined_score, first_line, second_line))
    
    # Return highest scoring pair
    if pairs:
        pairs.sort(key=lambda x: x[0], reverse=True)
        _, line1, line2 = pairs[0]
        # Pad/trim to exactly 44 characters
        return [line1.ljust(44, "<")[:44], line2.ljust(44, "<")[:44]]
    
    # Fallback: take two highest-scoring individual lines
    if len(candidates) >= 2:
        candidates.sort(key=lambda x: x[1], reverse=True)
        selected = sorted(candidates[:2], key=lambda x: x[0])
        line1 = selected[0][2].ljust(44, "<")[:44]
        line2 = selected[1][2].ljust(44, "<")[:44]
        return [line1, line2]
    
    return []


def parse_mrz_date(mrz_date: str) -> Optional[str]:
    """Parse MRZ date format (YYMMDD) to ISO format"""
    try:
        if len(mrz_date) != 6 or not mrz_date.isdigit():
            return None
        
        yy = int(mrz_date[0:2])
        mm = int(mrz_date[2:4])
        dd = int(mrz_date[4:6])
        
        # Determine century (ICAO convention: 00-99)
        # Typically: 00-30 = 2000-2030, 31-99 = 1931-1999
        year = 2000 + yy if yy <= 30 else 1900 + yy
        
        # Basic date validation
        if not (1 <= mm <= 12 and 1 <= dd <= 31):
            return None
        
        return f"{year:04d}-{mm:02d}-{dd:02d}"
    except:
        return None


def parse_passport_mrz(text: str) -> Dict[str, Any]:
    """
    Parse and validate TD3 passport MRZ with ICAO check digits.
    
    TD3 MRZ Structure:
    Line 1 (44 chars): P<ISSUING_COUNTRY<<SURNAME<<GIVEN_NAMES<<<<<<...
    Line 2 (44 chars): PASSPORT_NO<CD<NATIONALITY<DOB<CD<SEX<EXPIRY<CD<PERSONAL_NO<CD<COMPOSITE_CD
    
    Where CD = Check Digit
    """
    lines = extract_mrz_lines(text)

    if len(lines) < 2:
        return {
            "detected": False,
            "parsed": False,
            "valid": False,
            "status": "NOT_AVAILABLE",
            "validation_count": 0,
            "validations": {},
            "fields": {},
            "lines": [],
        }

    line1 = lines[0]
    line2 = lines[1]

    try:
        # Parse Line 1: P<ISSUING_COUNTRY<<SURNAME<<GIVEN_NAMES
        doc_type = line1[0]
        issuing_country = line1[2:5].replace("<", "").strip()
        
        name_section = line1[5:44]
        name_parts = name_section.split("<<")
        surname = name_parts[0].replace("<", " ").strip()
        given_names = name_parts[1].replace("<", " ").strip() if len(name_parts) > 1 else ""

        # Parse Line 2 fields and check digits
        passport_number = line2[0:9].replace("<", "").strip()
        passport_check = line2[9]
        
        nationality = line2[10:13].replace("<", "").strip()
        
        dob_raw = line2[13:19]
        dob_check = line2[19]
        dob_formatted = parse_mrz_date(dob_raw)
        
        sex = line2[20]
        
        expiry_raw = line2[21:27]
        expiry_check = line2[27]
        expiry_formatted = parse_mrz_date(expiry_raw)
        
        personal_number = line2[28:42].replace("<", "").strip()
        personal_check = line2[42]
        
        composite_check = line2[43]

        # Validate all check digits
        validations = {
            "passport_number": validate_mrz_check_digit(line2[0:9], passport_check),
            "date_of_birth": validate_mrz_check_digit(line2[13:19], dob_check),
            "expiry_date": validate_mrz_check_digit(line2[21:27], expiry_check),
            "personal_number": validate_mrz_check_digit(line2[28:42], personal_check) if personal_number else True,
        }

        # Composite check digit validates entire Line 2 (except final digit)
        composite_data = line2[0:10] + line2[13:20] + line2[21:43]
        validations["composite"] = validate_mrz_check_digit(composite_data, composite_check)

        # Count valid checks
        validation_count = sum(validations.values())
        
        # Check if passport is expired
        is_expired = False
        if expiry_formatted:
            try:
                expiry_date = datetime.strptime(expiry_formatted, "%Y-%m-%d").date()
                is_expired = expiry_date < datetime.now().date()
            except:
                pass

        # Technical consistency checks between parsed MRZ fields.
        consistency_issues: List[str] = []

        if doc_type != "P":
            consistency_issues.append("MRZ document type is not a standard passport TD3 code.")

        if not re.fullmatch(r"[A-Z]{3}", issuing_country or ""):
            consistency_issues.append("Issuing country code is invalid.")

        if not re.fullmatch(r"[A-Z]{3}", nationality or ""):
            consistency_issues.append("Nationality code is invalid.")

        if sex not in {"M", "F", "<"}:
            consistency_issues.append("Sex field is invalid.")

        if not dob_formatted:
            consistency_issues.append("Date of birth could not be parsed.")

        if not expiry_formatted:
            consistency_issues.append("Expiry date could not be parsed.")

        return {
            "detected": True,
            "parsed": True,
            "valid": validation_count >= 4,  # At least 4/5 checks must pass
            "status": (
                "VALID"
                if validation_count >= 4 and not consistency_issues
                else "REVIEW_REQUIRED"
                if validation_count >= 4
                else "CHECK_DIGIT_FAILED"
            ),
            "algorithm": "ICAO 9303 (7-3-1 weighting)",
            "validation_count": validation_count,
            "validations": validations,
            "consistency_valid": len(consistency_issues) == 0,
            "consistency_issues": consistency_issues,
            "authenticity_status": (
                "TECHNICAL_CHECKS_PASSED"
                if validation_count >= 4 and not consistency_issues and not is_expired
                else "EXPIRED_DOCUMENT"
                if is_expired
                else "SUSPICIOUS_TECHNICAL_SIGNAL"
            ),
            "fields": {
                "document_type": doc_type,
                "issuing_country": issuing_country,
                "surname": surname,
                "given_names": given_names,
                "passport_number": passport_number,
                "nationality": nationality,
                "date_of_birth": dob_formatted,
                "sex": sex,
                "expiry_date": expiry_formatted,
                "personal_number": personal_number,
                "is_expired": is_expired,
            },
            "lines": [line1, line2],
            "note": (
                "MRZ check digits validated using ICAO 9303 standard. "
                "Passing check digits indicates mathematical consistency, "
                "not legal authenticity."
            ),
        }

    except Exception as e:
        return {
            "detected": True,
            "parsed": False,
            "valid": False,
            "status": "PARSE_ERROR",
            "validation_count": 0,
            "validations": {},
            "fields": {},
            "lines": [line1, line2],
            "error": str(e),
        }


# ============================================================
# DRIVING LICENCE (IMPROVED VALIDATION)
# ============================================================

def _normalize_dl_candidate(value: str) -> Optional[str]:
    """Normalize Indian DL number candidate with OCR correction."""
    raw = re.sub(r"[^A-Z0-9]", "", (value or "").upper())

    # Indian DL format: typically 13-16 characters
    # Structure: STATE(2) + RTO/DISTRICT(2) + YEAR(4) + SERIAL(7)
    # Example: MH0120200001234 or KA0520150123456
    if len(raw) < 8 or len(raw) > 16:
        return None

    chars = list(raw)

    # First 2 characters: State code (letters)
    # Next 2 characters: RTO/district code (typically digits)
    # Positions 2-3 should be digits
    for index in range(2, min(4, len(chars))):
        if chars[index].isalpha():
            ocr_digit_map = {
                "O": "0",
                "Q": "0",
                "D": "0",
                "I": "1",
                "L": "1",
                "Z": "2",
                "S": "5",
                "G": "6",
                "B": "8",
            }
            chars[index] = ocr_digit_map.get(chars[index], chars[index])

    candidate = "".join(chars)

    # Validate structure: 2 letters + rest digits (flexible length)
    if re.fullmatch(r"[A-Z]{2}\d{6,14}", candidate):
        return candidate

    return None


def extract_dl_number(text: str) -> Optional[str]:
    """Extract Driving Licence number with separator tolerance."""
    upper = (text or "").upper()
    if not upper.strip():
        return None

    candidates = []

    # Pattern 1: Standard DL with common separators
    # Examples: MH-01-2020-0001234, KA 05 2015 0123456
    patterns = [
        r"(?<![A-Z0-9])([A-Z]{2}[\s./-]?\d{2}[\s./-]?\d{4}[\s./-]?\d{7})(?![A-Z0-9])",
        r"(?<![A-Z0-9])([A-Z]{2}[\s./-]?\d{2}[\s./-]?\d{11})(?![A-Z0-9])",
        r"(?<![A-Z0-9])([A-Z]{2}\d{11,13})(?![A-Z0-9])",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, upper):
            candidate = _normalize_dl_candidate(match.group(1))
            if candidate and candidate not in candidates:
                candidates.append(candidate)

    # Pattern 2: DL keyword-based extraction
    dl_keyword_pattern = re.compile(
        r"(?:DL\s*(?:NO|NUMBER|#)?|LICENCE\s*(?:NO|NUMBER)?|LICENSE\s*(?:NO|NUMBER)?)"
        r"\s*[:\-]?\s*"
        r"([A-Z]{2}[\s./-]?[A-Z0-9]{2}[\s./-]?[A-Z0-9]{4,12})",
        re.IGNORECASE
    )
    
    for match in dl_keyword_pattern.finditer(text):
        candidate = _normalize_dl_candidate(match.group(1))
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    # Pattern 3: Line-level extraction with unusual separators
    for line in upper.splitlines():
        compact = re.sub(r"[^A-Z0-9]", "", line)
        if 8 <= len(compact) <= 16:
            candidate = _normalize_dl_candidate(compact)
            if candidate and candidate not in candidates:
                candidates.append(candidate)

    return candidates[0] if candidates else None


def extract_dl_dates(text: str) -> Dict[str, Optional[str]]:
    """Extract date fields from DL OCR text."""
    dates = {}
    
    # Common date patterns in Indian DLs
    date_patterns = [
        (r"(?:DATE OF BIRTH|DOB|Birth)\s*[:\-]?\s*(\d{2}[/-]\d{2}[/-]\d{4})", "dob"),
        (r"(?:DATE OF ISSUE|ISSUE DATE|Issued)\s*[:\-]?\s*(\d{2}[/-]\d{2}[/-]\d{4})", "issue_date"),
        (r"(?:VALID FROM|Valid From)\s*[:\-]?\s*(\d{2}[/-]\d{2}[/-]\d{4})", "valid_from"),
        (r"(?:VALID TILL|VALID UPTO|Valid Till|Expiry)\s*[:\-]?\s*(\d{2}[/-]\d{2}[/-]\d{4})", "valid_till"),
    ]
    
    for pattern, field_name in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        dates[field_name] = match.group(1) if match else None
    
    return dates


def validate_driving_licence(text: str) -> Dict[str, Any]:
    """
    Validate Indian Driving Licence using structural rules.
    
    Note: Indian DL does NOT have a universal public checksum algorithm.
    Validation is structural only.
    """
    number = extract_dl_number(text)

    if not number:
        return {
            "number_found": False,
            "format_valid": False,
            "status": "NOT_AVAILABLE",
            "official_verification": "NOT_PERFORMED",
        }

    # Validate format: 2 state letters + 6-14 digits
    format_valid = bool(re.fullmatch(r"[A-Z]{2}\d{6,14}", number))

    # Extract components
    state_code = number[:2] if len(number) >= 2 else None
    
    # Extract dates
    dates = extract_dl_dates(text)
    
    # Check date validity
    date_issues = []
    is_expired = False
    
    if dates.get("valid_till"):
        try:
            expiry_date = datetime.strptime(
                dates["valid_till"].replace("-", "/"),
                "%d/%m/%Y"
            ).date()
            is_expired = expiry_date < datetime.now().date()
            
            if is_expired:
                date_issues.append("Licence appears expired")
        except:
            date_issues.append("Invalid expiry date format")
    
    # Validate date logic
    if dates.get("issue_date") and dates.get("valid_till"):
        try:
            issue = datetime.strptime(
                dates["issue_date"].replace("-", "/"),
                "%d/%m/%Y"
            ).date()
            expiry = datetime.strptime(
                dates["valid_till"].replace("-", "/"),
                "%d/%m/%Y"
            ).date()
            
            if expiry < issue:
                date_issues.append("Expiry date precedes issue date")
        except:
            pass

    # Mask sensitive portions
    mask_length = max(0, len(number) - 6)
    masked_number = number[:4] + ("X" * mask_length) + number[-2:] if len(number) > 6 else number

    # Additional technical consistency checks.
    consistency_issues: List[str] = list(date_issues)

    if state_code not in {
        "AP", "AR", "AS", "BR", "CG", "GA", "GJ", "HR", "HP", "JH",
        "KA", "KL", "MP", "MH", "MN", "ML", "MZ", "NL", "OD", "PB",
        "RJ", "SK", "TN", "TS", "TR", "UP", "UK", "WB", "AN", "CH",
        "DD", "DL", "DN", "JK", "LA", "LD", "PY",
    }:
        consistency_issues.append("State code is not recognized.")

    # A licence expiry date should not precede its issue date.
    # This is already checked above; preserve the signal in the response.
    consistency_valid = len(consistency_issues) == 0

    return {
        "number_found": True,
        "number": number,
        "masked_number": masked_number,
        "format_valid": format_valid,
        "state_code": state_code,
        "dates": dates,
        "is_expired": is_expired,
        "date_issues": date_issues,
        "consistency_valid": consistency_valid,
        "consistency_issues": consistency_issues,
        "status": (
            "EXPIRED" if is_expired
            else "REVIEW_REQUIRED" if format_valid and not consistency_valid
            else "STRUCTURALLY_VALID" if format_valid
            else "FORMAT_FAILED"
        ),
        "official_verification": "NOT_PERFORMED",
        "authenticity_status": (
            "EXPIRED_DOCUMENT"
            if is_expired
            else "TECHNICAL_CHECKS_PASSED"
            if format_valid and consistency_valid
            else "SUSPICIOUS_TECHNICAL_SIGNAL"
        ),
        "note": (
            "Driving Licence number structure, state code and available date "
            "consistency were checked locally. These checks do not prove legal "
            "authenticity. Official Parivahan/Sarathi verification is required."
        ),
    }


# ============================================================
# VOTER ID / EPIC (UNCHANGED - PRESERVED)
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
# GSTIN (UNCHANGED - PRESERVED)
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
# VISA (UNCHANGED - PRESERVED)
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