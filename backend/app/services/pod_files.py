"""Validation and storage shared by manual and downstream POD ingestion."""
import hashlib
import logging
from pathlib import Path
from uuid import UUID, uuid4

from app.core.config import PROJECT_ROOT, Settings, get_settings


POD_MAX_FILES = 2
POD_MAX_BYTES = 10 * 1024 * 1024
POD_FILE_TYPES = {
    ".pdf": ("PDF", "application/pdf", (b"%PDF",)),
    ".jpg": ("JPEG", "image/jpeg", (b"\xff\xd8\xff",)),
    ".jpeg": ("JPEG", "image/jpeg", (b"\xff\xd8\xff",)),
    ".png": ("PNG", "image/png", (b"\x89PNG\r\n\x1a\n",)),
}
POD_ALLOWED_FORMATS = "PDF, JPEG, or PNG"
IMPORTED_POD_MEDIA_TYPES = {
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
logger = logging.getLogger(__name__)


def validate_pod_content(filename: str, content: bytes) -> dict:
    filename = Path(filename.replace("\\", "/")).name
    extension = Path(filename).suffix.lower()
    file_type = POD_FILE_TYPES.get(extension)
    if file_type is None:
        raise ValueError(f"{filename} must be a {POD_ALLOWED_FORMATS} file")
    format_label, media_type, signatures = file_type
    payload = _pod_payload(filename, content, media_type)
    if not content.startswith(signatures):
        raise ValueError(f"{filename} must be a valid {format_label} file")
    return payload


def validate_imported_pod_content(filename: str, content: bytes) -> dict:
    """Keep authenticated AJ attachments in their source format for download.

    AJ's API does not limit PODs to the manual upload formats. Other source
    formats are stored as opaque attachments, without parsing or conversion.
    """
    filename = Path(filename.replace("\\", "/")).name
    extension = Path(filename).suffix.lower()
    if extension in POD_FILE_TYPES:
        return validate_pod_content(filename, content)
    media_type = IMPORTED_POD_MEDIA_TYPES.get(extension, "application/octet-stream")
    return _pod_payload(filename, content, media_type)


def _pod_payload(filename: str, content: bytes, media_type: str) -> dict:
    if not filename or filename in {".", ".."}:
        raise ValueError("POD filename is required")
    if not content:
        raise ValueError(f"{filename} is empty")
    if len(content) > POD_MAX_BYTES:
        raise ValueError(f"{filename} exceeds the size limit")
    return {
        "original_filename": filename, "content_type": media_type,
        "content": content, "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(), "extension": Path(filename).suffix.lower(),
    }


def storage_root(settings: Settings | None = None) -> Path:
    root = (settings or get_settings()).upload_storage_dir
    return root if root.is_absolute() else PROJECT_ROOT / root


def save_pod_content(upload_id: UUID, payload: dict, settings: Settings | None = None) -> dict:
    directory = storage_root(settings) / str(upload_id) / "pod"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid4().hex}{payload['extension']}"
    try:
        path.write_bytes(payload["content"])
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return {**payload, "storage_path": str(path)}


def delete_pod_content(path: str, settings: Settings | None = None) -> None:
    root = storage_root(settings).resolve()
    target = Path(path).resolve()
    if target.is_relative_to(root):
        try:
            target.unlink(missing_ok=True)
        except OSError:
            logger.warning("Unable to remove POD file %s", target, exc_info=True)
