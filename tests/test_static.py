"""Tests for static file serving and cache headers (Task 10)."""


def test_index_served_with_no_cache(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-cache"
    assert "type=\"module\"" in r.text
    assert "app.js?v=" not in r.text  # module entry must NOT be versioned


def test_healthz_no_store(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"


def test_index_has_reindex_button(client):
    r = client.get("/")
    assert 'id="btn-reindex"' in r.text


def test_vendor_assets_immutable_cache(client):
    r = client.get("/static/vendor/echarts.min.js")
    assert r.status_code == 200
    assert "immutable" in r.headers["cache-control"]
    assert "max-age=31536000" in r.headers["cache-control"]


def test_search_js_tiene_verificacion_de_hash(client):
    r = client.get("/static/js/search.js")
    assert r.status_code == 200
    assert "btn-verify" in r.text
    assert "/api/hash" in r.text
    assert "Idénticos" in r.text


def test_tree_component_servido(client):
    r = client.get("/static/js/tree.js")
    assert r.status_code == 200
    assert "export function mountTree" in r.text
    assert "explorer.tree_error" in r.text


def test_recoverable_js_usa_el_componente_de_arbol(client):
    r = client.get("/static/js/recoverable.js")
    assert 'from "./tree.js"' in r.text
    assert "mountTree" in r.text
    # la copia privada del árbol ha desaparecido
    assert "expandNode" not in r.text
    assert "buildChildrenHtml" not in r.text


def test_search_js_tiene_arbol_y_sin_campo_carpeta(client):
    r = client.get("/static/js/search.js")
    assert 'from "./tree.js"' in r.text
    assert "search.scope" in r.text
    assert "f-path" not in r.text  # el campo "Carpeta (acotar a)" desaparece


def test_pager_component_servido_y_search_lo_usa(client):
    r = client.get("/static/js/pager.js")
    assert r.status_code == 200
    assert "export function renderPager" in r.text
    s = client.get("/static/js/search.js").text
    assert 'from "./pager.js"' in s
    assert "_pageWindow" not in s  # la copia privada desaparece


def test_recoverable_y_explorer_usan_pager(client):
    rec = client.get("/static/js/recoverable.js").text
    ex = client.get("/static/js/explorer.js").text
    assert 'from "./pager.js"' in rec and "renderPager(" in rec
    assert 'from "./pager.js"' in ex and "renderPager(" in ex
    # los paginadores manuales prev/next desaparecen
    assert "prevBtn" not in rec
    assert "prevBtn" not in ex


def test_placeholders_de_carga(client):
    tree = client.get("/static/js/tree.js").text
    assert "common.loading" in tree
    search = client.get("/static/js/search.js").text
    assert "search.empty_hint" in search
    # el texto en español sigue existiendo, ahora en el diccionario i18n
    es = client.get("/static/js/locales/es.js").text
    assert "Cargando…" in es
    assert "Usa un preset o lanza una búsqueda." in es
