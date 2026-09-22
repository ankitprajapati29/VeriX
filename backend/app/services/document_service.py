from pathlib import Path


UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


def save_uploaded_file(filename: str, content: bytes) -> str:
    """
    Save an uploaded document locally and return its path.
    """

    safe_name = Path(filename).name
    file_path = UPLOAD_DIR / safe_name

    file_path.write_bytes(content)

    return str(file_path)