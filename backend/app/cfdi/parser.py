"""Parser for CFDI 4.0 XML invoices issued through the SAT.

Uses defusedxml to protect against XML attacks (billion laughs, XXE),
since invoices are user-uploaded, untrusted input.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from xml.etree.ElementTree import Element

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

from .models import Invoice, InvoiceType, LineItem, Party, Tax, TaxCode

NS = {
    "cfdi": "http://www.sat.gob.mx/cfd/4",
    "tfd": "http://www.sat.gob.mx/TimbreFiscalDigital",
}

SUPPORTED_VERSION = "4.0"


class CFDIParseError(ValueError):
    """Raised when an XML file is not a valid CFDI 4.0 invoice."""


def parse_cfdi(xml: bytes | str) -> Invoice:
    """Parse a CFDI 4.0 XML document into an Invoice."""
    try:
        root = SafeET.fromstring(xml)
    except DefusedXmlException as exc:
        raise CFDIParseError(f"Unsafe XML rejected: {exc}") from exc
    except SafeET.ParseError as exc:
        raise CFDIParseError(f"Malformed XML: {exc}") from exc

    if root.tag != f"{{{NS['cfdi']}}}Comprobante":
        raise CFDIParseError("Root element is not cfdi:Comprobante (CFDI 4.0)")

    version = root.get("Version")
    if version != SUPPORTED_VERSION:
        raise CFDIParseError(f"Unsupported CFDI version: {version!r}")

    issuer_el = _require(root, "cfdi:Emisor")
    receiver_el = _require(root, "cfdi:Receptor")
    taxes_el = root.find("cfdi:Impuestos", NS)

    return Invoice(
        uuid=_parse_uuid(root),
        version=version,
        invoice_type=_parse_invoice_type(root.get("TipoDeComprobante")),
        issued_at=_parse_datetime(_attr(root, "Fecha")),
        issuer=Party(
            rfc=_attr(issuer_el, "Rfc"),
            name=issuer_el.get("Nombre", ""),
            tax_regime=issuer_el.get("RegimenFiscal"),
        ),
        receiver=Party(
            rfc=_attr(receiver_el, "Rfc"),
            name=receiver_el.get("Nombre", ""),
            tax_regime=receiver_el.get("RegimenFiscalReceptor"),
        ),
        currency=_attr(root, "Moneda"),
        subtotal=_decimal(_attr(root, "SubTotal"), "SubTotal"),
        total=_decimal(_attr(root, "Total"), "Total"),
        discount=_optional_decimal(root.get("Descuento"), "Descuento") or Decimal("0"),
        exchange_rate=_optional_decimal(root.get("TipoCambio"), "TipoCambio"),
        series=root.get("Serie"),
        folio=root.get("Folio"),
        payment_method=root.get("MetodoPago"),
        payment_form=root.get("FormaPago"),
        cfdi_use=receiver_el.get("UsoCFDI"),
        items=tuple(_parse_item(el) for el in root.findall("cfdi:Conceptos/cfdi:Concepto", NS)),
        total_transferred=_optional_decimal(
            taxes_el.get("TotalImpuestosTrasladados") if taxes_el is not None else None,
            "TotalImpuestosTrasladados",
        )
        or Decimal("0"),
        total_withheld=_optional_decimal(
            taxes_el.get("TotalImpuestosRetenidos") if taxes_el is not None else None,
            "TotalImpuestosRetenidos",
        )
        or Decimal("0"),
    )


def _parse_item(el: Element) -> LineItem:
    return LineItem(
        product_key=_attr(el, "ClaveProdServ"),
        description=el.get("Descripcion", ""),
        quantity=_decimal(_attr(el, "Cantidad"), "Cantidad"),
        unit_key=_attr(el, "ClaveUnidad"),
        unit_price=_decimal(_attr(el, "ValorUnitario"), "ValorUnitario"),
        amount=_decimal(_attr(el, "Importe"), "Importe"),
        discount=_optional_decimal(el.get("Descuento"), "Descuento") or Decimal("0"),
        transferred=tuple(
            _parse_tax(t) for t in el.findall("cfdi:Impuestos/cfdi:Traslados/cfdi:Traslado", NS)
        ),
        withheld=tuple(
            _parse_tax(t) for t in el.findall("cfdi:Impuestos/cfdi:Retenciones/cfdi:Retencion", NS)
        ),
    )


def _parse_tax(el: Element) -> Tax:
    code = _attr(el, "Impuesto")
    try:
        tax = TaxCode(code)
    except ValueError as exc:
        raise CFDIParseError(f"Unknown tax code: {code!r}") from exc

    # Withholdings omit TipoFactor in some generators; SAT rules imply "Tasa".
    factor_type = el.get("TipoFactor", "Tasa")
    exempt = factor_type == "Exento"
    return Tax(
        tax=tax,
        base=_decimal(_attr(el, "Base"), "Base"),
        factor_type=factor_type,
        rate=None if exempt else _decimal(_attr(el, "TasaOCuota"), "TasaOCuota"),
        amount=Decimal("0") if exempt else _decimal(_attr(el, "Importe"), "Importe"),
    )


def _parse_uuid(root: Element) -> str | None:
    stamp = root.find("cfdi:Complemento/tfd:TimbreFiscalDigital", NS)
    if stamp is None:
        return None  # unstamped draft: valid structure but not a fiscal document yet
    uuid = stamp.get("UUID")
    return uuid.upper() if uuid else None


def _parse_invoice_type(value: str | None) -> InvoiceType:
    try:
        return InvoiceType(value)
    except ValueError as exc:
        raise CFDIParseError(f"Unknown TipoDeComprobante: {value!r}") from exc


def _parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise CFDIParseError(f"Invalid Fecha: {value!r}") from exc


def _require(root: Element, path: str) -> Element:
    el = root.find(path, NS)
    if el is None:
        raise CFDIParseError(f"Missing required element: {path}")
    return el


def _attr(el: Element, name: str) -> str:
    value = el.get(name)
    if value is None or value == "":
        tag = el.tag.split("}")[-1]
        raise CFDIParseError(f"Missing required attribute {name!r} on {tag}")
    return value


def _decimal(value: str, field_name: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise CFDIParseError(f"Invalid number in {field_name}: {value!r}") from exc


def _optional_decimal(value: str | None, field_name: str) -> Decimal | None:
    return None if value in (None, "") else _decimal(value, field_name)
