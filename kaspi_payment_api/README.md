# Kaspi Payment API

A FastAPI provider interface for Kaspi.kz online payment requests. The service accepts GET requests from trusted IPs, validates `check` and `pay` commands, stores order payments, and returns JSON or XML responses.

## Features

- GET `/payment` endpoint for `check` and `pay`
- IP allowlist for Kaspi source addresses
- HTTPS enforcement via headers
- SQLAlchemy + PostgreSQL/SQLite integration
- Request logging and idempotent duplicate `pay` handling by `txn_id`
- Bank payment date storage from `txn_date` for accounting reconciliation
- JSON and XML response support

## Project structure

```
kaspi_payment_api/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── kaspi.py
│   └── security.py
├── alembic/
│   ├── env.py
│   └── versions/
├── requirements.txt
└── README.md
```

## Setup

1. Create a Python virtual environment and install dependencies:

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

2. Create a `.env` file from the example and configure environment variables:

```bash
copy .env.example .env
```

Then edit `.env` to set your PostgreSQL connection and allowed source IPs:

```text
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/kaspi_payment
ALLOWED_IPS=194.187.247.152,194.187.245.108,197.187.244.108
ACCOUNT_REGEX=^[A-Za-z0-9_.@#\-]{1,200}$
TRUST_PROXY_HEADERS=true
SQL_ECHO=false
```

3. Run the application:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

If you do not use a `.env` file, set the same variables in your system environment before start.

4. Apply database migrations when running against an existing database:

```bash
alembic upgrade head
```


## Example request

```text
GET /payment?command=check&txn_id=1234567&account=4957835959&sum=200.00
```

```text
GET /payment?command=pay&txn_id=1234567&account=4957835959&sum=200.00&txn_date=20260501153045
```

## Order synchronization

Create an `accounts` row when the ticket order is created on your site. Use `account` as the unique order identifier passed to Kaspi, `balance_due` as the exact amount to pay, and `status='active'` while the order is payable.

Optional display data for Kaspi can be saved in `accounts.extra_fields` as JSON with keys like `field1`, `field2`, etc. These keys are returned in successful `check` responses under the protocol's `fields` object.

```json
{
  "field1": {"@name": "row", "#text": "3"},
  "field2": {"@name": "seat", "#text": "12"}
}
```

Simple values are also accepted, for example `{"field1": "row 3"}`. In that case the field name defaults to the field key.

Supported order statuses:

- `active`: returns `result=0`
- `canceled`: returns `result=2`
- `paid`: returns `result=3`
- `processing`: returns `result=4`

## Notes

- Use Nginx or another reverse proxy to provide TLS/HTTPS and forward `X-Forwarded-Proto`.
- Keep `TRUST_PROXY_HEADERS=true` only when the app is behind a trusted proxy that overwrites `X-Forwarded-For`.
- The app is designed for concurrent access and can handle multiple simultaneous requests.
