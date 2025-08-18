from typing import Optional, Union
from pydantic import BaseModel, field_validator
from pydantic.config import ConfigDict

NumberLike = Union[float, str]

class Summary(BaseModel):
    type: Optional[str] = None
    fipId: Optional[str] = None
    branch: Optional[str] = None
    status: Optional[str] = None
    fipName: Optional[str] = None
    currency: Optional[str] = None
    facility: Optional[str] = None
    ifscCode: Optional[str] = None
    micrCode: Optional[str] = None
    exchgeRate: Optional[NumberLike] = None
    openingDate: Optional[str] = None          # keep as string per your schema
    account_type: Optional[str] = None
    drawingLimit: Optional[NumberLike] = None
    linkedAccRef: Optional[str] = None
    fnrkAccountId: Optional[str] = None
    currentBalance: Optional[NumberLike] = None
    currentODLimit: Optional[NumberLike] = None
    pending_amount: Optional[NumberLike] = None
    balanceDateTime: Optional[int] = None       # epoch ms
    maskedAccNumber: Optional[str] = None
    accountAgeInDays: Optional[int] = None
    pending_transactionType: Optional[str] = None

    # pydantic v2 config (equivalent to extra = "allow")
    model_config = ConfigDict(extra="allow")

    # --- helpers ---
    @staticmethod
    def _blank_to_none(v):
        return None if isinstance(v, str) and v.strip() == "" else v

    @staticmethod
    def _to_int_or_none(v):
        v = Summary._blank_to_none(v)
        if v is None:
            return None
        try:
            return int(v)
        except Exception:
            try:
                return int(float(str(v).replace(",", "")))
            except Exception:
                return None

    # --- validators ---
    @field_validator("balanceDateTime", "accountAgeInDays", mode="before")
    def _int_fields(cls, v):
        return cls._to_int_or_none(v)

    @field_validator("exchgeRate", "drawingLimit", "currentBalance", "currentODLimit", "pending_amount", mode="before")
    def _numeric_unions(cls, v):
        v = cls._blank_to_none(v)
        if v is None:
            return None
        s = str(v).replace(",", "").strip()
        try:
            # parse to float when possible (schema also allows string)
            return float(s)
        except Exception:
            return v
