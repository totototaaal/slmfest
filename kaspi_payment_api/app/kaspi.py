from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Dict, Optional
from xml.etree import ElementTree

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models
from .security import format_amount, get_client_ip, validate_account

FIELD_NAME_RE = re.compile(r"^field\d+$")


class KaspiProcessor:
    def __init__(self, db: Session) -> None:
        self.db = db

    def process(self, request: Request, params: Dict[str, str]) -> Any:
        command = params.get("command", "").strip().lower()
        txn_id_str = params.get("txn_id", "").strip()
        txn_date_raw = params.get("txn_date", "").strip()
        account_value = params.get("account", "").strip()
        raw_sum = params.get("sum")
        response_format = self._determine_response_format(request, params)

        if command not in {"check", "pay"}:
            return self._respond(
                {"txn_id": txn_id_str, "result": 5, "comment": "Неизвестная команда"},
                request,
                params,
                command,
                account_value,
                response_format,
            )

        txn_id = self._parse_txn_id(txn_id_str)
        if txn_id is None:
            return self._respond(
                {"txn_id": txn_id_str, "result": 5, "comment": "Неверный txn_id"},
                request,
                params,
                command,
                account_value,
                response_format,
            )

        if not account_value or not validate_account(account_value):
            return self._respond(
                {"txn_id": txn_id_str, "result": 5, "comment": "Неверный идентификатор заказа"},
                request,
                params,
                command,
                account_value,
                response_format,
            )

        if command == "check":
            return self._check(request, params, txn_id_str, account_value, response_format)

        return self._pay(request, params, txn_id, txn_id_str, txn_date_raw, account_value, raw_sum, response_format)

    def _check(
        self,
        request: Request,
        params: Dict[str, str],
        txn_id_str: str,
        account_value: str,
        response_format: str,
    ) -> Any:
        account = self._get_account(account_value)
        payload = self._account_state_payload(txn_id_str, account)
        return self._respond(payload, request, params, "check", account_value, response_format)

    def _pay(
        self,
        request: Request,
        params: Dict[str, str],
        txn_id: int,
        txn_id_str: str,
        txn_date_raw: str,
        account_value: str,
        raw_sum: Optional[str],
        response_format: str,
    ) -> Any:
        previous_payment = self._get_payment(txn_id)
        if previous_payment:
            payload = self._payment_payload(previous_payment)
            return self._respond(payload, request, params, "pay", account_value, response_format)

        txn_date = self._parse_txn_date(txn_date_raw)
        if txn_date is None:
            return self._respond(
                {"txn_id": txn_id_str, "result": 5, "comment": "Неверный или отсутствующий txn_date"},
                request,
                params,
                "pay",
                account_value,
                response_format,
            )

        payment_sum = self._parse_sum(raw_sum)
        if payment_sum is None or payment_sum <= 0:
            return self._respond(
                {"txn_id": txn_id_str, "result": 5, "comment": "Неверная сумма платежа"},
                request,
                params,
                "pay",
                account_value,
                response_format,
            )

        account = self._get_account(account_value, lock=True)
        state_payload = self._account_state_payload(txn_id_str, account)
        if state_payload["result"] != 0:
            return self._respond(state_payload, request, params, "pay", account_value, response_format)

        balance_due = Decimal(account.balance_due).quantize(Decimal("0.01"))
        if payment_sum != balance_due:
            return self._respond(
                {"txn_id": txn_id_str, "result": 5, "comment": "Сумма платежа не совпадает с суммой заказа"},
                request,
                params,
                "pay",
                account_value,
                response_format,
            )

        new_payment = models.Payment(
            txn_id=txn_id,
            account_id=account.id,
            command="pay",
            sum=payment_sum,
            txn_date=txn_date,
            txn_date_raw=txn_date_raw,
        )

        try:
            self.db.add(new_payment)
            self.db.flush()
            new_payment.prv_txn = new_payment.id
            account.balance_due = Decimal("0.00")
            account.status = "paid"
            self.db.commit()
            self.db.refresh(new_payment)
        except IntegrityError:
            self.db.rollback()
            previous_payment = self._get_payment(txn_id)
            if previous_payment:
                payload = self._payment_payload(previous_payment)
                return self._respond(payload, request, params, "pay", account_value, response_format)
            return self._respond(
                {"txn_id": txn_id_str, "result": 5, "comment": "Ошибка записи платежа"},
                request,
                params,
                "pay",
                account_value,
                response_format,
            )

        payload = self._payment_payload(new_payment)
        return self._respond(payload, request, params, "pay", account_value, response_format)

    def _account_state_payload(self, txn_id: str, account: Optional[models.Account]) -> Dict[str, Any]:
        if not account:
            return {"txn_id": txn_id, "result": 1, "comment": "Заказ не найден"}
        if account.status == "canceled":
            return {"txn_id": txn_id, "result": 2, "comment": "Заказ отменён"}
        if account.status == "paid":
            return {"txn_id": txn_id, "result": 3, "comment": "Заказ уже оплачен"}
        if account.status == "processing":
            return {"txn_id": txn_id, "result": 4, "comment": "Платеж в обработке"}
        if not account.can_be_paid:
            return {"txn_id": txn_id, "result": 2, "comment": "Заказ отменён"}

        payload: Dict[str, Any] = {
            "txn_id": txn_id,
            "result": 0,
            "sum": format_amount(Decimal(account.balance_due)),
            "comment": "ОК",
        }
        payload.update(self._response_fields(account))
        return payload

    def _payment_payload(self, payment: models.Payment) -> Dict[str, Any]:
        return {
            "txn_id": str(payment.txn_id),
            "prv_txn_id": str(payment.prv_txn),
            "sum": format_amount(Decimal(payment.sum)),
            "result": 0,
            "comment": "ОК",
        }

    def _response_fields(self, account: models.Account) -> Dict[str, Dict[str, Dict[str, str]]]:
        if not isinstance(account.extra_fields, dict):
            return {}
        fields: Dict[str, Dict[str, str]] = {}
        for key, value in account.extra_fields.items():
            field_key = str(key)
            if not FIELD_NAME_RE.fullmatch(field_key) or value is None:
                continue
            if isinstance(value, dict):
                name = value.get("@name") or value.get("name") or field_key
                text = value.get("#text") or value.get("text") or value.get("value") or ""
            else:
                name = field_key
                text = value
            fields[field_key] = {"@name": str(name), "#text": str(text)}
        return {"fields": fields} if fields else {}

    def _respond(
        self,
        payload: Dict[str, Any],
        request: Request,
        params: Dict[str, str],
        command: Optional[str],
        account_value: Optional[str],
        response_format: str,
    ) -> Any:
        self._log_request(payload, request, params, command, account_value)
        return self._build_response(payload, response_format)

    def _build_response(self, payload: Dict[str, Any], fmt: str) -> Any:
        if fmt == "xml":
            return PlainTextResponse(
                content=self._to_xml(payload),
                media_type="application/xml; charset=utf-8",
            )
        return JSONResponse(content=payload, media_type="application/json; charset=utf-8")

    def _to_xml(self, payload: Dict[str, Any]) -> str:
        root = ElementTree.Element("response")
        for key, value in payload.items():
            if value is None:
                continue
            if key == "fields" and isinstance(value, dict):
                fields = ElementTree.SubElement(root, "fields")
                for field_key, field_value in value.items():
                    if not FIELD_NAME_RE.fullmatch(str(field_key)) or not isinstance(field_value, dict):
                        continue
                    child = ElementTree.SubElement(
                        fields,
                        str(field_key),
                        {"name": str(field_value.get("@name", ""))},
                    )
                    child.text = str(field_value.get("#text", ""))
                continue

            xml_key = "prv_txn" if key == "prv_txn_id" else str(key)
            child = ElementTree.SubElement(root, xml_key)
            child.text = str(value)
        return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")

    def _determine_response_format(self, request: Request, params: Dict[str, str]) -> str:
        if params.get("format", "").strip().lower() == "xml":
            return "xml"
        accept_header = request.headers.get("accept", "").lower()
        if "application/xml" in accept_header or "text/xml" in accept_header:
            return "xml"
        return "json"

    def _parse_txn_id(self, txn_id: str) -> Optional[int]:
        if not txn_id.isdigit() or len(txn_id) > 18:
            return None
        parsed = int(txn_id)
        return parsed if parsed > 0 else None

    def _parse_txn_date(self, txn_date: str) -> Optional[datetime]:
        if len(txn_date) != 14 or not txn_date.isdigit():
            return None
        try:
            return datetime.strptime(txn_date, "%Y%m%d%H%M%S")
        except ValueError:
            return None

    def _parse_sum(self, sum_value: Optional[str]) -> Optional[Decimal]:
        if sum_value is None:
            return None
        try:
            return Decimal(sum_value).quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError):
            return None

    def _get_account(self, account_value: str, lock: bool = False) -> Optional[models.Account]:
        query = self.db.query(models.Account).filter(models.Account.account == account_value)
        if lock:
            query = query.with_for_update()
        return query.one_or_none()

    def _get_payment(self, txn_id: int) -> Optional[models.Payment]:
        return self.db.query(models.Payment).filter(models.Payment.txn_id == txn_id).one_or_none()

    def _log_request(
        self,
        payload: Dict[str, Any],
        request: Request,
        params: Dict[str, str],
        command: Optional[str],
        account: Optional[str],
    ) -> None:
        try:
            txn_id = self._parse_txn_id(str(payload.get("txn_id", "")))
            request_log = models.RequestLog(
                txn_id=txn_id,
                command=command,
                account=account,
                client_ip=get_client_ip(request),
                params=dict(params),
                response_payload=payload,
                result=int(payload.get("result", 5)),
                comment=str(payload.get("comment", "")),
            )
            self.db.add(request_log)
            self.db.commit()
        except HTTPException:
            raise
        except Exception:
            self.db.rollback()
