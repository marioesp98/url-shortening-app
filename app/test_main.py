from fastapi.testclient import TestClient

from .main import app
from .rdb import get_redis


class FakeRedis:
    def __init__(self):
        # Let's pretend we have some data in Redis already.
        self.data = {
            "api-key:123": "123",
            "api-key:456": "456",
            "rate-limit:456:/api/v1/shorten": 0,
        }

    # We only need to implement the methods we use in the app (i.e. a subset of the Redis API).
    # The rest of the methods can be implemented as needed.

    def setnx(self, name: str, value: str) -> bool:
        if name not in self.data:
            self.data[name] = value
            return True
        return False

    def set(self, name: str, value: str) -> None:
        self.data[name] = value

    def get(self, name: str) -> str:
        return self.data.get(name)

    def decrby(self, name: str, amount: int = 1) -> None:
        self.data[name] -= amount

    def expire(self, name: str, time) -> None:
        # We don't need to implement this method for the tests we have.
        pass


_fake_redis = FakeRedis()


def override_get_redis():
    return _fake_redis


app.dependency_overrides[get_redis] = override_get_redis

client = TestClient(app)


def test_health_check():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_issue_api_key():
    response = client.post("/api/v1/issue/api_key")
    assert response.status_code == 200
    assert response.json().keys() == {"api_key", "expires_at", "issued_at"}


def test_shorten_url():
    response = client.post("/api/v1/shorten", json={"url": "https://www.google.com"}, headers={"X-Api-Key": "123"})
    assert response.status_code == 200
    assert response.text == '"/r/8ffdefbdec"'


def test_shorten_url_invalid_api_key():
    response = client.post("/api/v1/shorten", json={"url": "https://www.google.com"}, headers={"X-Api-Key": "abc"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid API key"}


def test_shorten_url_invalid_url():
    response = client.post("/api/v1/shorten", json={"url": "google"}, headers={"X-Api-Key": "123"})
    assert response.status_code == 422
    assert response.json() == {
        "detail": [{"loc": ["body", "url"], "msg": "invalid or missing URL scheme", "type": "value_error.url.scheme"}]
    }


def test_shorten_url_rate_limit():
    response = client.post("/api/v1/shorten", json={"url": "https://www.google.com"}, headers={"X-Api-Key": "456"})
    assert response.status_code == 429
    assert response.json() == {"detail": "Rate limit exceeded"}
