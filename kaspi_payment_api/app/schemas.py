from typing import Any, Dict, Optional

from pydantic import BaseModel

class KaspiResponse(BaseModel):
    txn_id: str
    result: int
    comment: Optional[str] = ""
    prv_txn_id: Optional[str] = None
    sum: Optional[str] = None
    fields: Optional[Dict[str, Any]] = None

    class Config:
        orm_mode = True
