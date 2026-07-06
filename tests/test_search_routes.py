from tests.helpers import add_entry


def test_search_endpoint(client, store_conn):
    _, conn = store_conn
    add_entry(conn, "x.bin", "/d", size=1024, owner="abc")
    add_entry(conn, "x_small.bin", "/d", size=10)   # lo filtra size_min
    add_entry(conn, "other.bin", "/d", size=5000)   # lo filtra name
    r = client.get("/api/search", params={"name": "x", "size_min": 100})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "x.bin"
    assert body["items"][0]["owner"] == "abc"
    assert r.headers["Cache-Control"] == "no-store"


def test_search_endpoint_path_filter(client, store_conn):
    _, conn = store_conn
    add_entry(conn, "dentro.bin", "/data/Sub", size=100)
    add_entry(conn, "fuera.bin", "/data/Otro", size=100)
    r = client.get("/api/search", params={"path": "/data/Sub"})
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "dentro.bin"


def test_search_endpoint_category_filter(client, store_conn):
    _, conn = store_conn
    add_entry(conn, "peli.mp4", "/d", size=100, extension="mp4")
    add_entry(conn, "doc.pdf", "/d", size=100, extension="pdf")
    r = client.get("/api/search", params={"category": "video"})
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "peli.mp4"


def test_search_endpoint_sort_and_order(client, store_conn):
    _, conn = store_conn
    add_entry(conn, "bravo.txt", "/d", size=10, extension="txt")
    add_entry(conn, "alfa.txt", "/d", size=20, extension="txt")
    r = client.get("/api/search", params={"ext": "txt", "sort": "name", "order": "asc"})
    body = r.json()
    assert [i["name"] for i in body["items"]] == ["alfa.txt", "bravo.txt"]


def test_dupes_endpoint(client, store_conn):
    _, conn = store_conn
    add_entry(conn, "a.iso", "/data/A", size=1_048_576)
    add_entry(conn, "b.iso", "/data/B", size=1_048_576)
    add_entry(conn, "unique.iso", "/data/C", size=2_000_000)  # sin pareja
    r = client.get("/api/dupes")
    assert r.status_code == 200
    body = r.json()
    assert body["groups"][0]["count"] == 2
    assert body["groups"][0]["size"] == 1_048_576
    assert r.headers["Cache-Control"] == "no-store"


def test_search_endpoint_group_pagination(client, store_conn):
    _, conn = store_conn
    add_entry(conn, "dup1_a.bin", "/data/A", size=2000)
    add_entry(conn, "dup1_b.bin", "/data/B", size=2000)
    add_entry(conn, "dup2_a.bin", "/data/A", size=1000)
    add_entry(conn, "dup2_b.bin", "/data/B", size=1000)
    add_entry(conn, "solo.bin", "/data/A", size=500)
    r = client.get("/api/search", params={
        "dupes_only": "true", "group_limit": 1, "group_offset": 0})
    assert r.status_code == 200
    body = r.json()
    assert body["total_groups"] == 2
    assert [i["size"] for i in body["items"]] == [2000, 2000]
    r2 = client.get("/api/search", params={
        "dupes_only": "true", "group_limit": 1, "group_offset": 1})
    assert [i["size"] for i in r2.json()["items"]] == [1000, 1000]
