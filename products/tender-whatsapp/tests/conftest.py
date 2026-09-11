import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    settings = Settings(secret_key="test-secret", database_url=f"sqlite:///{tmp_path}/test.db")
    app = create_app(settings)
    with TestClient(app) as c:
        yield c
