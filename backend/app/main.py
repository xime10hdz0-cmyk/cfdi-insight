"""CFDI Insight API."""

from fastapi import FastAPI, HTTPException, UploadFile

from .cfdi import CFDIParseError, TaxCode, parse_cfdi

MAX_UPLOAD_BYTES = 1_000_000  # CFDI files are small; reject anything suspicious

app = FastAPI(title="CFDI Insight", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/invoices/parse")
async def parse_invoice(file: UploadFile) -> dict:
    """Parse an uploaded CFDI XML and return a summary (not persisted yet)."""
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large")

    try:
        invoice = parse_cfdi(content)
    except CFDIParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "uuid": invoice.uuid,
        "type": invoice.invoice_type.value,
        "issued_at": invoice.issued_at.isoformat(),
        "issuer": {"rfc": invoice.issuer.rfc, "name": invoice.issuer.name},
        "receiver": {"rfc": invoice.receiver.rfc, "name": invoice.receiver.name},
        "currency": invoice.currency,
        "subtotal": str(invoice.subtotal),
        "total": str(invoice.total),
        "total_mxn": str(invoice.total_mxn),
        "iva_transferred": str(invoice.transferred_by_tax(TaxCode.IVA)),
        "iva_withheld": str(invoice.withheld_by_tax(TaxCode.IVA)),
        "isr_withheld": str(invoice.withheld_by_tax(TaxCode.ISR)),
        "items": len(invoice.items),
    }
