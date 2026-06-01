from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from . import models, schemas
from .database import SessionLocal, engine
from .kaspi import KaspiProcessor
from .quick_payment import create_fast_payment
from .security import validate_https, validate_request_origin

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Kaspi Payment API", version="1.0")


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/payment")
async def payment(request: Request, db: Session = Depends(get_db)):
    validate_https(request)
    validate_request_origin(request)
    params = {key: value for key, value in request.query_params.items()}
    processor = KaspiProcessor(db)
    response = processor.process(request, params)
    return response


@app.post("/kaspi/create-payment", response_model=schemas.CreatePaymentResponse)
async def create_payment(payload: schemas.CreatePaymentRequest, db: Session = Depends(get_db)):
    return create_fast_payment(db, payload)


@app.get("/payment-success", response_class=HTMLResponse)
async def payment_success():
    return """
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Оплата принята</title>
  <style>
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      font-family: Arial, sans-serif;
      background: #f6f7f9;
      color: #1f2933;
    }
    main {
      width: min(520px, calc(100% - 32px));
      text-align: center;
    }
    h1 {
      margin: 0 0 12px;
      font-size: 32px;
      line-height: 1.2;
    }
    p {
      margin: 0;
      font-size: 17px;
      line-height: 1.5;
    }
  </style>
</head>
<body>
  <main>
    <h1>Оплата принята</h1>
    <p>Спасибо. Статус заказа обновится после подтверждения платежа Kaspi.</p>
  </main>
</body>
</html>
"""


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
