from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

try:
    from pydantic import ConfigDict
except ImportError:  # pragma: no cover - pydantic v1 compatibility
    ConfigDict = None


class OrmBaseModel(BaseModel):
    if ConfigDict is not None:
        model_config = ConfigDict(from_attributes=True)
    else:
        class Config:
            orm_mode = True


class KaspiResponse(OrmBaseModel):
    txn_id: str
    result: int
    comment: Optional[str] = ""
    prv_txn_id: Optional[str] = None
    sum: Optional[str] = None
    fields: Optional[Dict[str, Any]] = None


class CreatePaymentRequest(BaseModel):
    order_id: str = Field(..., min_length=1, max_length=16)
    amount: int = Field(..., gt=0, le=9223372036854775807, description="Payment amount in tiyn")
    generate_qr_code: bool = False
    return_url: Optional[str] = Field(default=None, max_length=1024)
    referer_host: Optional[str] = Field(default=None, max_length=1024)


class CreatePaymentResponse(OrmBaseModel):
    id: int
    tran_id: str
    order_id: str
    amount: int
    status: str
    redirect_url: Optional[str] = None
    qr_code_image: Optional[str] = None
    kaspi_code: Optional[int] = None
    kaspi_message: Optional[str] = None
