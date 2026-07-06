from app.schema import (
    F, TYPE_FILE, TYPE_DIR, ROOT_PATH, category_for_extension,
    extensions_for_category, ALL_CATEGORIZED_EXTS,
)


def test_field_map_has_core_fields():
    for key in ("name", "parent_path", "size", "type", "extension", "mtime", "atime"):
        assert key in F


def test_type_constants():
    assert TYPE_FILE == "file"
    assert TYPE_DIR == "directory"


def test_root_path_constant():
    assert ROOT_PATH == "/data"


def test_category_for_extension():
    assert category_for_extension("mp4") == "video"
    assert category_for_extension(".JPG") == "image"
    assert category_for_extension("pdf") == "document"
    assert category_for_extension("xyz") == "other"
    assert category_for_extension(None) == "other"
    assert category_for_extension("") == "other"


def test_extensions_for_category_returns_known_set():
    exts = extensions_for_category("video")
    assert "mp4" in exts and "mkv" in exts
    assert "pdf" not in exts


def test_extensions_for_category_unknown_returns_empty_set():
    assert extensions_for_category("other") == set()
    assert extensions_for_category("noexiste") == set()


def test_all_categorized_exts_is_union_of_categories():
    assert "mp4" in ALL_CATEGORIZED_EXTS
    assert "pdf" in ALL_CATEGORIZED_EXTS
    assert "py" in ALL_CATEGORIZED_EXTS
    assert "xyz" not in ALL_CATEGORIZED_EXTS
    # es la unión exacta de todas las categorías conocidas
    union = set()
    for cat in ("video", "image", "audio", "document", "archive", "code"):
        union |= extensions_for_category(cat)
    assert ALL_CATEGORIZED_EXTS == frozenset(union)
