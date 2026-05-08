from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_and_get_product():
    payload = {"name": "Test Product", "price": "9.99"}
    response = client.post("/api/products", json=payload)
    assert response.status_code == 200
    product_id = response.json()["id"]

    response = client.get(f"/api/products/{product_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Test Product"
