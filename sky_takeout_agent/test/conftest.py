import pytest
from starlette.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    """全局注入测试客户端，在所有测试用例间复用"""
    with TestClient(app) as test_client:
        yield test_client