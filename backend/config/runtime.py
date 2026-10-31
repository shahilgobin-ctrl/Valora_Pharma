"""Resolve an optional shared local data directory without committing PC paths."""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


def data_directory(base_dir):
    base_dir = Path(base_dir)
    value = os.environ.get("DJANGO_DATA_DIR", "").strip()
    if not value:
        pointer = base_dir / ".data-directory"
        value = pointer.read_text(encoding="utf-8-sig").strip() if pointer.is_file() else ""
    directory = Path(value).expanduser() if value else base_dir
    if not directory.is_absolute():
        directory = base_dir / directory
    directory = directory.resolve()
    if not directory.is_dir():
        raise ImproperlyConfigured("The configured pharmacy data directory does not exist.")
    return directory
