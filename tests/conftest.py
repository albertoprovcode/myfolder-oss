import os

os.environ["AUTO_REINDEX"] = "0"  # los tests no deben disparar crawls
os.environ["HASH_DB_PATH"] = "/tmp/myfolder-tests-hashes.db"

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.storage import get_store
from tests.helpers import make_store


@pytest.fixture
def store_conn(tmp_path):
    return make_store(tmp_path)


@pytest.fixture
def client(store_conn):
    store, _ = store_conn
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
