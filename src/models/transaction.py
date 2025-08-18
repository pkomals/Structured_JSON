from typing import Optional, Union
from pydantic import BaseModel

class Transaction(BaseModel):
    """Single transaction row."""
    mode: Optional[str] = None                        # OTHERS/NEFT/UPI/...
    type: Optional[str] = None                        # CREDIT/DEBIT
    fipId: Optional[str] = None
    txnId: Optional[str] = None
    amount: Optional[Union[float, str]] = None
    narration: Optional[str] = None
    reference: Optional[str] = None
    valueDate: Optional[int] = None                   # epoch ms
    account_type: Optional[str] = None
    linkedAccRef: Optional[str] = None
    fnrkAccountId: Optional[str] = None
    currentBalance: Optional[Union[str, float]] = None
    maskedAccNumber: Optional[str] = None
    transactionTimestamp: Optional[int] = None        # epoch ms

    class Config:
        extra = "allow"
