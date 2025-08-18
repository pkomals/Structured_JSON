from typing import Optional
from pydantic import BaseModel

class TransactionsMeta(BaseModel):
    """Summary metadata about the transaction set for the account."""
    fipId: Optional[str] = None
    toTimestamp: Optional[int] = None                 # epoch ms
    linkedAccRef: Optional[str] = None
    fnrkAccountId: Optional[str] = None
    fromTimestamp: Optional[int] = None               # epoch ms
    maskedAccNumber: Optional[str] = None
    noOfTransactions: Optional[int] = None

    class Config:
        extra = "allow"
