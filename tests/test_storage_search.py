from tests.helpers import DEFAULT_EPOCH, add_entry, make_store


def _seed(conn):
    add_entry(conn, "IMG_20240612.jpg", "/data/Photo", size=500,
              extension="jpg", owner="alberto", group="users")
    add_entry(conn, "informe_2024.pdf", "/data/Documents", size=300,
              extension="pdf", owner="root", group="wheel",
              mtime=DEFAULT_EPOCH - 500 * 86400)
    add_entry(conn, "Photo", "/data", type="directory", size=500)


def test_search_substring_case_insensitive(tmp_path):
    store, conn = make_store(tmp_path)
    _seed(conn)
    r = store.search({"name": "40612"}, limit=10, offset=0)
    assert r["total"] == 1 and r["items"][0]["name"] == "IMG_20240612.jpg"
    assert r["items"][0]["path"] == "/data/Photo"
    assert store.search({"name": "img_2024"}, limit=10, offset=0)["total"] == 1
    assert store.search({"name": "noexiste"}, limit=10, offset=0)["total"] == 0


def test_search_short_query_falls_back_to_like(tmp_path):
    store, conn = make_store(tmp_path)
    _seed(conn)
    assert store.search({"name": "im"}, limit=10, offset=0)["total"] == 1


def test_search_filters(tmp_path):
    store, conn = make_store(tmp_path)
    _seed(conn)
    assert store.search({"ext": ".PDF"}, limit=10, offset=0)["total"] == 1
    assert store.search({"owner": "alberto"}, limit=10, offset=0)["total"] == 1
    assert store.search({"size_min": 400}, limit=10, offset=0)["total"] == 1
    assert store.search({"type": "directory"}, limit=10, offset=0)["total"] == 1
    # solo files por defecto
    assert store.search({}, limit=10, offset=0)["total"] == 2
    # rango de fechas: solo el pdf es viejo
    r = store.search({"mtime_to": "2023-01-01"}, limit=10, offset=0)
    assert r["total"] == 1 and r["items"][0]["name"] == "informe_2024.pdf"


def test_search_path_restricts_to_subtree(tmp_path):
    store, conn = make_store(tmp_path)
    _seed(conn)
    add_entry(conn, "otro.jpg", "/data/Otros", size=200, extension="jpg")
    r = store.search({"path": "/data/Photo"}, limit=10, offset=0)
    assert r["total"] == 1
    assert r["items"][0]["name"] == "IMG_20240612.jpg"


def test_search_category_video(tmp_path):
    store, conn = make_store(tmp_path)
    add_entry(conn, "peli.mp4", "/data/Videos", size=100, extension="mp4")
    add_entry(conn, "serie.mkv", "/data/Videos", size=100, extension="mkv")
    add_entry(conn, "informe.pdf", "/data/Documents", size=100, extension="pdf")
    r = store.search({"category": "video"}, limit=10, offset=0)
    assert r["total"] == 2
    names = {i["name"] for i in r["items"]}
    assert names == {"peli.mp4", "serie.mkv"}


def test_search_category_document(tmp_path):
    store, conn = make_store(tmp_path)
    add_entry(conn, "peli.mp4", "/data/Videos", size=100, extension="mp4")
    add_entry(conn, "informe.pdf", "/data/Documents", size=100, extension="pdf")
    add_entry(conn, "hoja.xlsx", "/data/Documents", size=100, extension="xlsx")
    r = store.search({"category": "document"}, limit=10, offset=0)
    assert r["total"] == 2
    names = {i["name"] for i in r["items"]}
    assert names == {"informe.pdf", "hoja.xlsx"}


def test_search_category_other_includes_no_ext_and_unknown_ext(tmp_path):
    store, conn = make_store(tmp_path)
    add_entry(conn, "peli.mp4", "/data/Videos", size=100, extension="mp4")
    add_entry(conn, "raro.xyz", "/data/Misc", size=100, extension="xyz")
    add_entry(conn, "sinext", "/data/Misc", size=100, extension=None)
    r = store.search({"category": "other"}, limit=10, offset=0)
    assert r["total"] == 2
    names = {i["name"] for i in r["items"]}
    assert names == {"raro.xyz", "sinext"}


def test_search_category_unknown_is_ignored(tmp_path):
    store, conn = make_store(tmp_path)
    _seed(conn)
    r_all = store.search({}, limit=10, offset=0)
    r_bogus = store.search({"category": "noexiste"}, limit=10, offset=0)
    assert r_bogus["total"] == r_all["total"]


def test_search_sort_name_asc(tmp_path):
    store, conn = make_store(tmp_path)
    add_entry(conn, "bravo.txt", "/data", size=10, extension="txt")
    add_entry(conn, "alfa.txt", "/data", size=20, extension="txt")
    add_entry(conn, "charlie.txt", "/data", size=30, extension="txt")
    r = store.search({"ext": "txt"}, limit=10, offset=0)
    # por defecto sigue siendo size desc
    assert [i["name"] for i in r["items"]] == ["charlie.txt", "alfa.txt", "bravo.txt"]


def test_search_sort_name_explicit_asc_and_desc(tmp_path):
    store, conn = make_store(tmp_path)
    add_entry(conn, "bravo.txt", "/data", size=10, extension="txt")
    add_entry(conn, "alfa.txt", "/data", size=20, extension="txt")
    add_entry(conn, "charlie.txt", "/data", size=30, extension="txt")
    r_asc = store.search({"ext": "txt", "sort": "name", "order": "asc"}, limit=10, offset=0)
    assert [i["name"] for i in r_asc["items"]] == ["alfa.txt", "bravo.txt", "charlie.txt"]
    r_desc = store.search({"ext": "txt", "sort": "name", "order": "desc"}, limit=10, offset=0)
    assert [i["name"] for i in r_desc["items"]] == ["charlie.txt", "bravo.txt", "alfa.txt"]


def test_search_sort_mtime_asc_and_desc(tmp_path):
    store, conn = make_store(tmp_path)
    add_entry(conn, "viejo.txt", "/data", size=10, extension="txt", mtime=DEFAULT_EPOCH - 1000)
    add_entry(conn, "medio.txt", "/data", size=10, extension="txt", mtime=DEFAULT_EPOCH)
    add_entry(conn, "nuevo.txt", "/data", size=10, extension="txt", mtime=DEFAULT_EPOCH + 1000)
    r_asc = store.search({"ext": "txt", "sort": "mtime", "order": "asc"}, limit=10, offset=0)
    assert [i["name"] for i in r_asc["items"]] == ["viejo.txt", "medio.txt", "nuevo.txt"]
    r_desc = store.search({"ext": "txt", "sort": "mtime", "order": "desc"}, limit=10, offset=0)
    assert [i["name"] for i in r_desc["items"]] == ["nuevo.txt", "medio.txt", "viejo.txt"]


def test_search_unknown_sort_or_order_falls_back_to_defaults(tmp_path):
    store, conn = make_store(tmp_path)
    add_entry(conn, "bravo.txt", "/data", size=10, extension="txt")
    add_entry(conn, "alfa.txt", "/data", size=20, extension="txt")
    r = store.search({"ext": "txt", "sort": "bogus", "order": "bogus"}, limit=10, offset=0)
    # cae a size desc (comportamiento por defecto)
    assert [i["name"] for i in r["items"]] == ["alfa.txt", "bravo.txt"]


def test_search_without_new_params_is_unchanged(tmp_path):
    store, conn = make_store(tmp_path)
    _seed(conn)
    r = store.search({"name": "img"}, limit=10, offset=0)
    assert r["total"] == 1
    assert r["items"][0]["name"] == "IMG_20240612.jpg"
    assert r["items"][0]["path"] == "/data/Photo"
    assert set(r["items"][0].keys()) == {
        "name", "path", "size", "size_h", "mtime", "atime", "owner", "group", "type",
    }


def test_dupes(tmp_path):
    store, conn = make_store(tmp_path)
    add_entry(conn, "a.iso", "/data/Backup", size=5_000_000)
    add_entry(conn, "b.iso", "/data/Video", size=5_000_000)
    add_entry(conn, "c.txt", "/data/Backup", size=5_000_000, extension="txt")
    add_entry(conn, "unico.bin", "/data/Backup", size=7_000_000)
    r = store.dupes(path=None, min_size=1_000_000, limit=10)
    assert r["groups"] == [{"size": 5_000_000, "size_h": "4.8 MB", "count": 3}]
    r2 = store.dupes(path="/data/Video", min_size=1_000_000, limit=10)
    assert r2["groups"] == []  # en /data/Video solo hay 1 de ese tamaño


def test_search_dupes_only(tmp_path):
    """dupes_only devuelve solo archivos cuyo tamaño exacto comparten >=2 archivos."""
    store, conn = make_store(tmp_path)
    add_entry(conn, "peli_A.mkv", "/data/Video", size=5_000_000)
    add_entry(conn, "peli_B.mkv", "/data/Video", size=5_000_000)   # comparte tamaño con A
    add_entry(conn, "unica.mkv", "/data/Video", size=9_999_999)    # tamaño único
    r = store.search({"dupes_only": True}, limit=10, offset=0)
    names = sorted(i["name"] for i in r["items"])
    assert names == ["peli_A.mkv", "peli_B.mkv"]
    assert r["total"] == 2
    # sin el flag, salen los tres
    assert store.search({}, limit=10, offset=0)["total"] == 3


def test_search_dupes_only_with_size_min(tmp_path):
    """dupes_only combina con size_min: solo duplicados por encima del umbral."""
    store, conn = make_store(tmp_path)
    add_entry(conn, "grande_A.mkv", "/data/Video", size=200_000_000)
    add_entry(conn, "grande_B.mkv", "/data/Video", size=200_000_000)
    add_entry(conn, "peque_A.txt", "/data/Docs", size=1000)
    add_entry(conn, "peque_B.txt", "/data/Docs", size=1000)
    r = store.search({"dupes_only": True, "size_min": 100_000_000}, limit=10, offset=0)
    assert sorted(i["name"] for i in r["items"]) == ["grande_A.mkv", "grande_B.mkv"]


def _seed_grupos(conn):
    """4 grupos de duplicados (tamaños 1000>900>800>700) + 1 tamaño único."""
    add_entry(conn, "g1_a.bin", "/data/A", size=1000)
    add_entry(conn, "g1_b.bin", "/data/B", size=1000)
    add_entry(conn, "g1_c.bin", "/data/C", size=1000)
    add_entry(conn, "g2_a.bin", "/data/A", size=900)
    add_entry(conn, "g2_b.bin", "/data/B", size=900)
    add_entry(conn, "g3_a.bin", "/data/A", size=800)
    add_entry(conn, "g3_b.bin", "/data/B", size=800)
    add_entry(conn, "g4_a.bin", "/data/A", size=700)
    add_entry(conn, "g4_b.bin", "/data/B", size=700)
    add_entry(conn, "unico.bin", "/data/A", size=500)


def test_search_dupes_group_pagination_no_parte_grupos(tmp_path):
    """Con group_limit se pagina por GRUPOS de tamaño: cada página trae todas
    las filas de sus grupos (un grupo nunca queda partido entre páginas)."""
    store, conn = make_store(tmp_path)
    _seed_grupos(conn)
    r = store.search({"dupes_only": True}, limit=200, offset=0,
                     group_limit=2, group_offset=0)
    # Página 1 (desc): grupos 1000 (3 filas) y 900 (2 filas) COMPLETOS
    assert [i["size"] for i in r["items"]] == [1000, 1000, 1000, 900, 900]
    assert r["total_groups"] == 4
    assert r["total"] == 9  # todas las filas duplicadas, en todas las páginas
    # Página 2: grupos 800 y 700
    r2 = store.search({"dupes_only": True}, limit=200, offset=0,
                      group_limit=2, group_offset=2)
    assert [i["size"] for i in r2["items"]] == [800, 800, 700, 700]
    # Página fuera de rango: vacía pero con los totales
    r3 = store.search({"dupes_only": True}, limit=200, offset=0,
                      group_limit=2, group_offset=4)
    assert r3["items"] == [] and r3["total_groups"] == 4


def test_search_dupes_group_pagination_orden_asc(tmp_path):
    store, conn = make_store(tmp_path)
    _seed_grupos(conn)
    r = store.search({"dupes_only": True, "order": "asc"}, limit=200, offset=0,
                     group_limit=2, group_offset=0)
    assert [i["size"] for i in r["items"]] == [700, 700, 800, 800]


def test_search_dupes_group_pagination_respeta_filtros(tmp_path):
    """La paginación por grupos convive con el resto de filtros (size_min)."""
    store, conn = make_store(tmp_path)
    _seed_grupos(conn)
    r = store.search({"dupes_only": True, "size_min": 850}, limit=200, offset=0,
                     group_limit=10, group_offset=0)
    assert [i["size"] for i in r["items"]] == [1000, 1000, 1000, 900, 900]
    assert r["total_groups"] == 2


def test_search_group_limit_sin_dupes_only_se_ignora(tmp_path):
    """Sin dupes_only, group_limit no cambia el comportamiento clásico."""
    store, conn = make_store(tmp_path)
    _seed_grupos(conn)
    r = store.search({}, limit=3, offset=0, group_limit=2, group_offset=0)
    assert len(r["items"]) == 3 and r["total"] == 10
    assert "total_groups" not in r
