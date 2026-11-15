"""Bounded PDF/DOCX attachments. Never execute or extract uploaded content."""

import base64
import io
import json
import zipfile
from pathlib import PurePosixPath
from pydantic import BaseModel, Field

MAX_BYTES = 10 * 1024 * 1024


class Attachment(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    data_base64: str = Field(min_length=1, max_length=14 * 1024 * 1024)


def envelope(attachment: Attachment) -> str:
    filename = attachment.filename
    if "/" in filename or "\\" in filename or any(ord(c) < 32 for c in filename):
        raise ValueError("Use a plain filename without paths or control characters.")
    data = base64.b64decode(attachment.data_base64, validate=True)
    if not data or len(data) > MAX_BYTES:
        raise ValueError("Attachment must be at most 10 MiB.")
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix == ".pdf" and data.startswith(b"%PDF-"):
        mime = "application/pdf"
    elif suffix == ".docx":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            files = archive.infolist()
            if (
                len(files) > 2000
                or sum(f.file_size for f in files) > 50 * 1024 * 1024
                or any(
                    f.flag_bits & 1
                    or f.filename.startswith("/")
                    or ".." in PurePosixPath(f.filename).parts
                    for f in files
                )
                or not {"[Content_Types].xml", "word/document.xml"}.issubset(
                    archive.namelist()
                )
                or any("vbaproject" in f.filename.lower() for f in files)
            ):
                raise ValueError("Unsupported or unsafe DOCX container.")
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        raise ValueError(
            "Only PDF and DOCX files with matching file signatures are accepted."
        )
    return json.dumps(
        {
            "quantumcare_attachment": 1,
            "filename": filename,
            "mime": mime,
            "data_base64": attachment.data_base64,
        },
        separators=(",", ":"),
    )
