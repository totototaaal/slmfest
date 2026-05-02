from decimal import Decimal
import re

from fastapi import HTTPException, Request, status

from .config import ACCOUNT_REGEX, ALLOWED_IPS, HTTPS_HEADER, HTTPS_VALUE, TRUST_PROXY_HEADERS

account_pattern = re.compile(ACCOUNT_REGEX)


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For") if TRUST_PROXY_HEADERS else None
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to determine client IP")


def validate_request_origin(request: Request) -> str:
    client_ip = get_client_ip(request)
    if client_ip not in ALLOWED_IPS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: invalid source IP")
    return client_ip


def validate_https(request: Request) -> None:
    header_value = request.headers.get(HTTPS_HEADER, "").lower()
    scheme = request.url.scheme.lower()
    if scheme != "https" and header_value != HTTPS_VALUE:
        raise HTTPException(status_code=status.HTTP_426_UPGRADE_REQUIRED, detail="HTTPS required")


def validate_account(account: str) -> bool:
    return bool(account_pattern.fullmatch(account))


def format_amount(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}"
