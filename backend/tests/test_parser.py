from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.cfdi import CFDIParseError, InvoiceType, TaxCode, parse_cfdi

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class TestProfessionalServicesInvoice:
    @pytest.fixture
    def invoice(self):
        return parse_cfdi(load("ingreso_honorarios.xml"))

    def test_header_fields(self, invoice):
        assert invoice.version == "4.0"
        assert invoice.invoice_type is InvoiceType.INGRESO
        assert invoice.series == "A"
        assert invoice.folio == "1024"
        assert invoice.issued_at == datetime(2026, 10, 15, 10, 30)
        assert invoice.payment_method == "PUE"

    def test_uuid_is_normalized_to_uppercase(self, invoice):
        assert invoice.uuid == "5F3A2B1C-9D8E-4F7A-B6C5-1234567890AB"

    def test_parties(self, invoice):
        assert invoice.issuer.rfc == "EKU9003173C9"
        assert invoice.issuer.tax_regime == "612"
        assert invoice.receiver.rfc == "XIA190128J61"
        assert invoice.cfdi_use == "G03"

    def test_amounts_are_exact_decimals(self, invoice):
        assert invoice.subtotal == Decimal("10000.00")
        assert invoice.total == Decimal("9533.33")
        assert invoice.total_mxn == Decimal("9533.33")

    def test_taxes_by_type(self, invoice):
        assert invoice.transferred_by_tax(TaxCode.IVA) == Decimal("1600.00")
        assert invoice.withheld_by_tax(TaxCode.ISR) == Decimal("1000.00")
        assert invoice.withheld_by_tax(TaxCode.IVA) == Decimal("1066.67")

    def test_item_taxes_match_invoice_totals(self, invoice):
        withheld = invoice.withheld_by_tax(TaxCode.ISR) + invoice.withheld_by_tax(TaxCode.IVA)
        assert withheld == invoice.total_withheld
        assert invoice.transferred_by_tax(TaxCode.IVA) == invoice.total_transferred

    def test_total_is_consistent(self, invoice):
        expected = (
            invoice.subtotal
            - invoice.discount
            + invoice.total_transferred
            - invoice.total_withheld
        )
        assert expected == invoice.total


class TestForeignCurrencyInvoice:
    @pytest.fixture
    def invoice(self):
        return parse_cfdi(load("ingreso_usd_multi.xml"))

    def test_converts_total_to_mxn(self, invoice):
        assert invoice.currency == "USD"
        assert invoice.exchange_rate == Decimal("18.5000")
        assert invoice.total_mxn == Decimal("5712.80")

    def test_multiple_items_with_discount(self, invoice):
        assert len(invoice.items) == 2
        assert invoice.items[0].discount == Decimal("20.00")
        assert invoice.discount == Decimal("20.00")

    def test_exempt_tax_has_no_rate_or_amount(self, invoice):
        exempt = invoice.items[1].transferred[0]
        assert exempt.factor_type == "Exento"
        assert exempt.rate is None
        assert exempt.amount == Decimal("0")

    def test_missing_withholdings_default_to_zero(self, invoice):
        assert invoice.total_withheld == Decimal("0")


class TestInvalidInput:
    def test_malformed_xml(self):
        with pytest.raises(CFDIParseError, match="Malformed XML"):
            parse_cfdi(b"<cfdi:Comprobante")

    def test_not_a_cfdi(self):
        with pytest.raises(CFDIParseError, match="not cfdi:Comprobante"):
            parse_cfdi(b"<root/>")

    def test_unsupported_version(self):
        xml = load("ingreso_honorarios.xml").replace(b'Version="4.0"', b'Version="3.3"', 1)
        with pytest.raises(CFDIParseError, match="Unsupported CFDI version"):
            parse_cfdi(xml)

    def test_missing_required_attribute(self):
        xml = load("ingreso_honorarios.xml").replace(b' Total="9533.33"', b"", 1)
        with pytest.raises(CFDIParseError, match="'Total'"):
            parse_cfdi(xml)

    def test_invalid_number(self):
        xml = load("ingreso_honorarios.xml").replace(
            b'SubTotal="10000.00"', b'SubTotal="diez mil"', 1
        )
        with pytest.raises(CFDIParseError, match="Invalid number in SubTotal"):
            parse_cfdi(xml)

    def test_rejects_entity_expansion_attack(self):
        xml = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;">]>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4">&lol2;</cfdi:Comprobante>"""
        with pytest.raises(CFDIParseError, match="Unsafe XML"):
            parse_cfdi(xml)

    def test_unstamped_invoice_has_no_uuid(self):
        xml = load("ingreso_honorarios.xml")
        start = xml.index(b"<cfdi:Complemento>")
        end = xml.index(b"</cfdi:Complemento>") + len(b"</cfdi:Complemento>")
        invoice = parse_cfdi(xml[:start] + xml[end:])
        assert invoice.uuid is None
