from pathlib import Path

from fastapi.testclient import TestClient

from app.main import MAX_UPLOAD_BYTES, app

client = TestClient(app)
FIXTURES = Path(__file__).parent / "fixtures"


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_parse_valid_invoice():
    xml = (FIXTURES / "ingreso_honorarios.xml").read_bytes()
    response = client.post("/invoices/parse", files={"file": ("factura.xml", xml, "text/xml")})

    assert response.status_code == 200
    body = response.json()
    assert body["uuid"] == "5F3A2B1C-9D8E-4F7A-B6C5-1234567890AB"
    assert body["total"] == "9533.33"
    assert body["isr_withheld"] == "1000.00"


def test_parse_invalid_invoice_returns_422():
    response = client.post("/invoices/parse", files={"file": ("x.xml", b"<nope", "text/xml")})
    assert response.status_code == 422


def test_rejects_oversized_upload():
    big = b"x" * (MAX_UPLOAD_BYTES + 1)
    response = client.post("/invoices/parse", files={"file": ("big.xml", big, "text/xml")})
    assert response.status_code == 413
