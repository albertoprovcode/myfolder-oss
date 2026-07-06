"""Single source of truth for the index shape (field names, types, categories).

Edit field names here only; the rest of the app references this module.
"""
from __future__ import annotations

F = {
    "name": "name",
    "parent_path": "parent_path",
    "size": "size",
    "size_du": "size_du",      # allocated/on-disk size
    "type": "type",
    "extension": "extension",
    "mtime": "mtime",
    "atime": "atime",
    "ctime": "ctime",
    "nlink": "nlink",
    "owner": "owner",
    "group": "group",
}

TYPE_FILE = "file"
TYPE_DIR = "directory"
TYPE_INDEXINFO = "indexinfo"
ROOT_PATH = "/data"

_CATEGORIES = {
    "video": {"mp4", "mkv", "avi", "mov", "wmv", "m4v", "mpg", "mpeg", "flv", "webm", "ts"},
    "image": {"jpg", "jpeg", "png", "gif", "heic", "raw", "tiff", "tif", "bmp", "webp", "cr2", "nef"},
    "audio": {"mp3", "flac", "wav", "aac", "ogg", "m4a", "wma", "opus"},
    "document": {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "odt", "ods", "csv", "md", "epub"},
    "archive": {"zip", "rar", "7z", "tar", "gz", "bz2", "xz", "iso"},
    "code": {"py", "js", "ts", "java", "c", "cpp", "go", "rs", "sh", "html", "css", "json", "yml", "yaml"},
}


def category_for_extension(ext: str | None) -> str:
    if not ext:
        return "other"
    clean = ext.lower().lstrip(".")
    for category, exts in _CATEGORIES.items():
        if clean in exts:
            return category
    return "other"


def extensions_for_category(cat: str) -> set[str]:
    """Set de extensiones (sin punto, minúsculas) de una categoría conocida.
    Vacío si `cat` no es una categoría de _CATEGORIES (incluye "other")."""
    return set(_CATEGORIES.get(cat, ()))


ALL_CATEGORIZED_EXTS: frozenset[str] = frozenset(
    ext for exts in _CATEGORIES.values() for ext in exts
)
