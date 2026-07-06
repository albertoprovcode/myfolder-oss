import os

from app.crawler.scan import WalkStats, walk_dir


def _tree(tmp_path):
    """Music/ con: a.mp3(100), sub/b.flac(200), sub/deep/c.txt(50)."""
    root = tmp_path / "Music"
    (root / "sub" / "deep").mkdir(parents=True)
    (root / "a.mp3").write_bytes(b"x" * 100)
    (root / "sub" / "b.flac").write_bytes(b"x" * 200)
    (root / "sub" / "deep" / "c.txt").write_bytes(b"x" * 50)
    return root


def test_walk_dir_rolls_up_and_postorder(tmp_path):
    root = _tree(tmp_path)
    rows = []
    totals = walk_dir(str(root), "Music", "/data", rows.append, WalkStats())
    assert totals.size == 350 and totals.files == 3 and totals.dirs == 2

    by_name = {(r["parent_path"], r["name"]): r for r in rows}
    music = by_name[("/data", "Music")]
    assert music["type"] == "directory"
    assert music["size"] == 350
    assert music["file_count"] == 3 and music["dir_count"] == 2
    assert music["size_norecurs"] == 100
    assert music["file_count_norecurs"] == 1 and music["dir_count_norecurs"] == 1

    sub = by_name[("/data/Music", "sub")]
    assert sub["size"] == 250 and sub["file_count"] == 2 and sub["dir_count"] == 1

    f = by_name[("/data/Music", "a.mp3")]
    assert f["type"] == "file" and f["size"] == 100 and f["extension"] == "mp3"
    assert isinstance(f["mtime"], int) and f["owner"]

    # post-orden: la fila de una carpeta va DESPUÉS de las de su subárbol
    order = [(r["parent_path"], r["name"]) for r in rows]
    assert order.index(("/data/Music/sub", "deep")) < order.index(("/data/Music", "sub"))
    assert order[-1] == ("/data", "Music")


def test_walk_dir_skips_symlinks_and_counts_errors(tmp_path):
    root = _tree(tmp_path)
    os.symlink(str(root / "a.mp3"), str(root / "link.mp3"))
    rows = []
    stats = WalkStats()
    totals = walk_dir(str(root), "Music", "/data", rows.append, stats)
    assert totals.files == 3  # el symlink no cuenta
    names = {r["name"] for r in rows}
    assert "link.mp3" not in names


def test_extension_rules(tmp_path):
    root = tmp_path / "X"
    root.mkdir()
    (root / "SIN_EXT").write_bytes(b"x")
    (root / "FOTO.JPG").write_bytes(b"x")
    rows = []
    walk_dir(str(root), "X", "/data", rows.append, WalkStats())
    by_name = {r["name"]: r for r in rows}
    assert by_name["SIN_EXT"]["extension"] is None
    assert by_name["FOTO.JPG"]["extension"] == "jpg"


from app.crawler.scan import load_ids, preseed_id_caches, _owner, _group


def test_load_ids_parsea_passwd(tmp_path):
    p = tmp_path / "passwd"
    p.write_text(
        "root:x:0:0:root:/root:/bin/sh\n"
        "alberto:x:1000:1000:Alberto:/home/alberto:/bin/sh\n"
        "# comentario\n"
        "malformada\n"
        "sin_id:x:no-numerico:0::/:/bin/sh\n",
        encoding="utf-8")
    ids = load_ids(str(p))
    assert ids == {0: "root", 1000: "alberto"}


def test_load_ids_fichero_inexistente(tmp_path):
    assert load_ids(str(tmp_path / "no-existe")) == {}


def test_preseed_resuelve_con_nombres_del_host(tmp_path):
    p = tmp_path / "passwd"
    p.write_text("alberto:x:65001:65001::/:/bin/sh\n", encoding="utf-8")
    g = tmp_path / "group"
    g.write_text("familia:x:65002:\n", encoding="utf-8")
    preseed_id_caches(str(p), str(g))
    try:
        assert _owner(65001) == "alberto"      # host gana
        assert _group(65002) == "familia"
        assert _owner(65003) == "65003"        # fallback actual intacto
    finally:
        preseed_id_caches("/no/existe", "/no/existe")  # limpia para otros tests
