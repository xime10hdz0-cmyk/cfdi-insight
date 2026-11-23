"""Domain models for a parsed CFDI 4.0 invoice.

Money values use Decimal (never float) to avoid rounding errors in tax math.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum


class InvoiceType(str, Enum):
    """TipoDeComprobante as defined by the SAT catalog c_TipoDeComprobante."""

    INGRESO = "I"  # income
    EGRESO = "E"  # credit note / expense
    TRASLADO = "T"  # transfer of goods
    NOMINA = "N"  # payroll
    PAGO = "P"  # payment complement


class TaxCode(str, Enum):
    """Impuesto codes from the SAT catalog c_Impuesto."""

    ISR = "001"
    IVA = "002"
    IEPS = "003"


@dataclass(frozen=True)
class Tax:
    """A single transferred (Traslado) or withheld (Retencion) tax."""

    tax: TaxCode
    base: Decimal
    factor_type: str  # Tasa, Cuota or Exento
    rate: Decimal | None  # None when factor_type is Exento
    amount: Decimal  # zero when Exento


@dataclass(frozen=True)
class Party:
    rfc: str
    name: str
    tax_regime: str | None = None


@dataclass(frozen=True)
class LineItem:
    """A Concepto: one product or service line of the invoice."""

    product_key: str  # ClaveProdServ
    description: str
    quantity: Decimal
    unit_key: str  # ClaveUnidad
    unit_price: Decimal
    amount: Decimal  # Importe (before discount and taxes)
    discount: Decimal = Decimal("0")
    transferred: tuple[Tax, ...] = ()
    withheld: tuple[Tax, ...] = ()


@dataclass(frozen=True)
class Invoice:
    uuid: str | None  # folio fiscal, from the TimbreFiscalDigital complement
    version: str
    invoice_type: InvoiceType
    issued_at: datetime
    issuer: Party
    receiver: Party
    currency: str
    subtotal: Decimal
    total: Decimal
    discount: Decimal = Decimal("0")
    exchange_rate: Decimal | None = None
    series: str | None = None
    folio: str | None = None
    payment_method: str | None = None  # MetodoPago: PUE / PPD
    payment_form: str | None = None  # FormaPago: 01 cash, 03 transfer...
    cfdi_use: str | None = None  # UsoCFDI of the receiver
    items: tuple[LineItem, ...] = field(default_factory=tuple)
    total_transferred: Decimal = Decimal("0")
    total_withheld: Decimal = Decimal("0")

    def transferred_by_tax(self, tax: TaxCode) -> Decimal:
        """Sum of a transferred tax across all line items."""
        return sum(
            (t.amount for item in self.items for t in item.transferred if t.tax == tax),
            Decimal("0"),
        )

    def withheld_by_tax(self, tax: TaxCode) -> Decimal:
        """Sum of a withheld tax across all line items."""
        return sum(
            (t.amount for item in self.items for t in item.withheld if t.tax == tax),
            Decimal("0"),
        )

    @property
    def total_mxn(self) -> Decimal:
        """Total converted to MXN using the invoice exchange rate."""
        if self.currency in ("MXN", "XXX") or self.exchange_rate is None:
            return self.total
        return (self.total * self.exchange_rate).quantize(Decimal("0.01"))
