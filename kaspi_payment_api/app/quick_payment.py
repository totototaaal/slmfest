from decimal import Decimal
import json
from typing import Any, Dict
from urllib import error, request
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models, schemas
from .config import (
    KASPI_FAST_PAYMENT_URL,
    KASPI_REFERER_HOST,
    KASPI_REQUEST_TIMEOUT,
    KASPI_RETURN_URL,
    KASPI_SERVICE_ID,
)


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

    if not order.redirect_url and not order.qr_code_image:
        order.status = "failed"
        order.kaspi_message = "Kaspi response does not contain redirectUrl or qrCodeImage"
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=order.kaspi_message)

    order.status = "payment_created"
    db.commit()
    db.refresh(order)
    return order


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
