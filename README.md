# CFDI Insight

Financial insights from Mexican electronic invoices (CFDI 4.0).

CFDI Insight parses the XML invoices issued through Mexico's tax authority (SAT),
categorizes income and expenses, estimates tax obligations (IVA / ISR), and shows
financial dashboards for freelancers and small businesses.

> **Status:** early, active development. The CFDI parser and a first API endpoint
> are implemented and tested; persistence, the dashboard and the AI layer are next.

## Why this is harder than it looks

- **CFDI structure:** an invoice can contain many line items, each with its own
  transferred and withheld taxes (IVA, ISR, IEPS), exempt items, discounts and
  foreign currencies.
- **Exact money math:** every amount is a `Decimal`; totals are cross-checked
  against line-level taxes.
- **Untrusted input:** XML is user-uploaded, so parsing uses `defusedxml` to block
  entity-expansion and XXE attacks, and uploads are size-limited.
- **Tax rules:** deductibility and monthly estimates depend on the taxpayer's
  regime and change over time, so they live in isolated, tested business logic.

## Tech stack

| Layer | Tech |
|---|---|
| Backend | Python 3.12+, FastAPI |
| Database (planned) | PostgreSQL + SQLAlchemy + Alembic |
| Frontend (planned) | React + Vite + Recharts |
| Testing | pytest |
| Infra (planned) | Docker Compose, GitHub Actions |

## Getting started

```bash
cd backend
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

pytest                         # run the tests
uvicorn app.main:app --reload  # API at http://localhost:8000/docs
```

Try it with a sample invoice:

```bash
curl -F "file=@tests/fixtures/ingreso_honorarios.xml" http://localhost:8000/invoices/parse
```

## Project structure

```
backend/
  app/
    cfdi/
      models.py   # domain models (Invoice, LineItem, Tax...)
      parser.py   # CFDI 4.0 XML parser with validation
    main.py       # FastAPI app
  tests/
    fixtures/     # fictional sample invoices
```

## Roadmap

### Phase 1 — Core parsing ✅ (in progress)
- [x] CFDI 4.0 parser: header, issuer, receiver, line items, taxes, UUID
- [x] Safe XML handling and validation errors
- [x] `POST /invoices/parse` endpoint
- [ ] Payment complement (Pagos 2.0) support for PPD invoices
- [ ] Credit notes (Egreso) linked to their original invoice (CfdiRelacionados)
- [ ] Validate that line-level taxes add up to the declared totals

### Phase 2 — Persistence & API
- [ ] PostgreSQL schema with SQLAlchemy models and Alembic migrations
- [ ] Bulk upload (ZIP with many XML files)
- [ ] Duplicate detection by UUID
- [ ] Filtering by date range, RFC, type and category
- [ ] Authentication and per-user data

### Phase 3 — Dashboard
- [ ] React app: upload, invoice list, invoice detail
- [ ] Monthly income vs. expenses charts
- [ ] Spending by category and by supplier

### Phase 4 — Tax logic
- [ ] Expense categorization rules (by ClaveProdServ and supplier)
- [ ] Deductibility rules by tax regime
- [ ] Monthly IVA and ISR estimates
- [ ] Export reports to Excel / PDF

### Phase 5 — AI agent
- [ ] Automatic expense classification with an LLM
- [ ] Natural-language questions over your invoices
  ("How much did I spend on fuel in March?")

## License

MIT
