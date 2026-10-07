from fastapi.testclient import TestClient

from biodiv import __version__
from biodiv.api.main import app


def test_health_reports_ok_and_version():
    res = TestClient(app).get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "version": __version__}
