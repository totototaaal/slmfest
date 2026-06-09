from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html import escape
import json
from typing import Any, Dict
from urllib import error, request
from urllib.parse import urlencode
from uuid import uuid4
import logging

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models, schemas
from .config import (
    KASPI_FAST_PAYMENT_URL,
    KASPI_ONLINE_URL,
    KASPI_REFERER_HOST,
    KASPI_REQUEST_TIMEOUT,
    KASPI_RETURN_URL,
    KASPI_SERVICE_ID,
)
from .security import validate_account

TIYIN_PER_TENGE = Decimal("100")

logger = logging.getLogger("kaspi.quick_payment")


def create_fast_payment(db: Session, payload: schemas.CreatePaymentRequest) -> models.Order:
    if not KASPI_SERVICE_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="KASPI_SERVICE_ID is not configured",
        )
    if len(KASPI_SERVICE_ID) > 64:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="KASPI_SERVICE_ID must be 64 characters or fewer",
        )

    order = db.query(models.Order).filter(models.Order.order_id == payload.order_id).one_or_none()
    if order:
        if order.amount != payload.amount:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Order already exists with a different amount",
            )
        if order.status == "paid":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Order is already paid")
        _ensure_payable_account(db, payload.order_id, payload.amount)
        db.commit()
        if order.redirect_url or order.qr_code_image:
            return order
    else:
        order = models.Order(
            tran_id=uuid4().hex,
            order_id=payload.order_id,
            amount=payload.amount,
            status="created",
        )
        db.add(order)
        _ensure_payable_account(db, payload.order_id, payload.amount)

    order.return_url = payload.return_url or KASPI_RETURN_URL
    order.referer_host = payload.referer_host or KASPI_REFERER_HOST

    try:
        db.commit()
        db.refresh(order)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Order already exists") from exc

    kaspi_payload = {
        "TranId": order.tran_id,
        "OrderId": order.order_id,
        "Amount": order.amount,
        "Service": KASPI_SERVICE_ID,
        "returnUrl": order.return_url,
        "refererHost": order.referer_host,
    }
    if payload.generate_qr_code:
        kaspi_payload["GenerateQrCode"] = True

    try:
        # Safe logging of parameters sent to Kaspi (no secrets)
        logger.info(
            "Calling Kaspi fast API",
            extra={
                "tran_id": order.tran_id,
                "order_id": order.order_id,
                "amount_tiyin": order.amount,
                "service": KASPI_SERVICE_ID,
                "return_url": order.return_url,
                "target_url": KASPI_FAST_PAYMENT_URL,
            },
        )
        kaspi_response = _post_json(kaspi_payload)
    except RuntimeError as exc:
        order.status = "failed"
        order.kaspi_message = str(exc)
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    order.kaspi_response = kaspi_response
    order.kaspi_code = _as_int(kaspi_response.get("code"))
    order.kaspi_message = str(kaspi_response.get("message") or "")
    order.redirect_url = kaspi_response.get("redirectUrl")
    order.qr_code_image = kaspi_response.get("qrCodeImage")

    if order.kaspi_code != 0:
        order.status = "failed"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=order.kaspi_message or "Kaspi returned an error",
        )

    if payload.generate_qr_code and not order.qr_code_image:
        order.status = "failed"
        order.kaspi_message = "Kaspi response does not contain qrCodeImage"
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=order.kaspi_message)

    if not payload.generate_qr_code and not order.redirect_url:
        order.status = "failed"
        order.kaspi_message = "Kaspi response does not contain redirectUrl"
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=order.kaspi_message)

    order.status = "payment_created"
    db.commit()
    db.refresh(order)
    return order


def build_quick_payment_test_page() -> str:
    # Modern responsive test page. Uses a plain HTML form POST to /quick-payment/build-form
    # so the backend (which calls Kaspi) runs server-side and returns the auto-submit form.
    return """
<!doctype html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Тестирование Kaspi Быстрая оплата</title>
    <style>
        :root { --bg: #ffffff; --muted: #6b7280; --border: #e6edf3; --input: #f8fafc; --blue: #0b69ff; }
        html,body { height:100%; margin:0; padding:0; font-family: Inter, system-ui, Arial, sans-serif; background:#f6f7f9; color:#0f1724 }
        .wrap { min-height:100vh; display:flex; align-items:center; justify-content:center; padding:24px }
        .card { width:100%; max-width:450px; background:var(--bg); border-radius:12px; box-shadow:0 8px 30px rgba(15,23,36,0.08); padding:26px; border:1px solid var(--border) }
        h1 { margin:0 0 8px; font-size:20px; color:#0f1724 }
        p.lead { margin:0 0 16px; color:var(--muted); font-size:14px }
        label { display:block; font-size:13px; color:#111827; margin-bottom:8px; font-weight:600 }
        .field { display:flex; flex-direction:column; gap:8px; margin-bottom:12px }
        input[type=text], input[type=number] { width:100%; padding:12px 14px; border:1px solid #d1d9e3; background:var(--input); border-radius:8px; font-size:15px; outline:none }
        input:focus { box-shadow:0 0 0 4px rgba(11,105,255,0.08); border-color:var(--blue) }
        .actions { display:flex; gap:12px; align-items:center; margin-top:8px }
        button.primary { background:var(--blue); color:#fff; border:0; padding:12px 16px; border-radius:8px; font-weight:700; cursor:pointer; flex:1 }
        .info { font-size:13px; color:var(--muted); margin-top:12px }
        .error { background:#fff5f5; border:1px solid #fecaca; color:#7f1d1d; padding:10px; border-radius:8px; margin-bottom:12px }
        @media (max-width:420px) { .card { padding:18px; border-radius:10px } h1 { font-size:18px } }
    </style>
</head>
<body>
    <div class="wrap">
        <main class="card" role="main">
            <h1>Тестирование Kaspi Быстрая оплата</h1>
            <p class="lead">Удобная страница для ручной проверки интеграции Kaspi Fast Payment.</p>

            <div id="error" style="display:none" class="error" role="alert"></div>

            <form id="testForm" method="post" action="/quick-payment/build-form">
                <div class="field">
                    <label for="order_id">Order ID</label>
                    <input id="order_id" name="order_id" type="text" maxlength="16" value="TEST001" required>
                </div>

                <div class="field">
                    <label for="amount">Amount (тенге)</label>
                    <input id="amount" name="amount_tenge" type="number" min="1" step="0.01" value="1000" required>
                </div>

                <div class="actions">
                    <button class="primary" type="submit">Оплатить через Kaspi</button>
                </div>

                <p class="info">TranId будет создан автоматически. Сумма отправляется в тиын. После оплаты произойдет возврат на <strong>/payment-success</strong>.</p>
            </form>
        </main>
    </div>
</body>
</html>
"""


def build_kaspi_form(db: Session, order_id: str, amount_tenge_raw: str) -> str:
    service = _get_service_id()
    cleaned_order_id = order_id.strip()
    if not cleaned_order_id or len(cleaned_order_id) > 16 or not validate_account(cleaned_order_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid order_id")

    amount_tenge, amount_tiyin = _parse_amount_tenge(amount_tenge_raw)
    tran_id = _build_tran_id(cleaned_order_id)
    return_url = _append_order_id(KASPI_RETURN_URL, cleaned_order_id)

    quick_order = models.QuickPaymentOrder(
        tran_id=tran_id,
        order_id=cleaned_order_id,
        amount_tenge=amount_tenge,
        amount_tiyin=amount_tiyin,
        service=service,
        return_url=return_url,
        status="created",
    )
    db.add(quick_order)
    _ensure_payable_account(db, cleaned_order_id, amount_tiyin)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Quick payment order already exists") from exc

    fields = {
        "TranId": tran_id,
        "OrderId": cleaned_order_id,
        "Amount": str(amount_tiyin),
        "Service": service,
        "returnUrl": return_url,
        # Include refererHost in the HTML form as some Kaspi flows expect it.
        "refererHost": KASPI_REFERER_HOST,
    }
    # Safe logging of parameters that will be submitted to Kaspi via browser
    logger.info(
        "Preparing Kaspi online form",
        extra={
            "tran_id": tran_id,
            "order_id": cleaned_order_id,
            "amount_tiyin": amount_tiyin,
            "service": service,
            "return_url": return_url,
            "target_url": KASPI_ONLINE_URL,
        },
    )
    return _auto_submit_form(KASPI_ONLINE_URL, fields)


def _ensure_payable_account(db: Session, order_id: str, amount: int) -> None:
    account = db.query(models.Account).filter(models.Account.account == order_id).one_or_none()
    balance_due = (Decimal(amount) / Decimal("100")).quantize(Decimal("0.01"))

    if account:
        if account.status == "paid":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account is already paid")
        if account.status == "canceled":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account is canceled")
        account.balance_due = balance_due
        account.can_be_paid = True
        if account.status != "processing":
            account.status = "active"
        return

    db.add(
        models.Account(
            account=order_id,
            status="active",
            balance_due=balance_due,
            can_be_paid=True,
        )
    )


def _get_service_id() -> str:
    if not KASPI_SERVICE_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="KASPI_SERVICE_ID is not configured",
        )
    if len(KASPI_SERVICE_ID) > 64:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="KASPI_SERVICE_ID must be 64 characters or fewer",
        )
    return KASPI_SERVICE_ID


def _parse_amount_tenge(raw_value: str) -> tuple[Decimal, int]:
    try:
        amount_tenge = Decimal(raw_value.strip().replace(",", "."))
    except (InvalidOperation, AttributeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid amount_tenge")

    if amount_tenge <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid amount_tenge")

    amount_tiyin_decimal = amount_tenge * TIYIN_PER_TENGE
    if amount_tiyin_decimal != amount_tiyin_decimal.to_integral_value():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="amount_tenge must have at most 2 decimals")

    amount_tiyin = int(amount_tiyin_decimal)
    return amount_tenge.quantize(Decimal("0.01")), amount_tiyin


def _build_tran_id(order_id: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{order_id}-{timestamp}-{uuid4().hex[:8]}"


def _append_order_id(base_url: str, order_id: str) -> str:
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode({'order_id': order_id})}"


def _auto_submit_form(action: str, fields: Dict[str, str]) -> str:
    hidden_inputs = "\n".join(
        f'    <input type="hidden" name="{escape(name, quote=True)}" value="{escape(value, quote=True)}">'
        for name, value in fields.items()
    )
    return f"""
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Переход в Kaspi</title>
</head>
<body onload="document.forms[0].submit()">
  <form action="{escape(action, quote=True)}" method="post">
{hidden_inputs}
    <noscript>
      <button type="submit">Оплатить через Kaspi</button>
    </noscript>
  </form>
</body>
</html>
"""


def _post_json(payload: Dict[str, Any]) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    kaspi_request = request.Request(
        KASPI_FAST_PAYMENT_URL,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(kaspi_request, timeout=KASPI_REQUEST_TIMEOUT) as response:
            response_body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Kaspi returned HTTP {exc.code}: {response_body[:500]}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Unable to reach Kaspi: {exc.reason}") from exc

    try:
        parsed = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Kaspi returned a non-JSON response") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError("Kaspi returned an unexpected response")
    return parsed


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
