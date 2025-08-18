from typing import Optional
from pydantic import BaseModel

class Profile(BaseModel):
    """Profile item for a bank statement (list element)."""
    dob: Optional[int] = None                         # epoch ms (can be negative)
    pan: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None                        # e.g., SINGLE/JOINT
    email: Optional[str] = None
    fipId: Optional[str] = None
    mobile: Optional[str] = None
    address: Optional[str] = None
    nominee: Optional[str] = None
    landLine: Optional[str] = None
    account_type: Optional[str] = None                # e.g., deposit, savings
    linkedAccRef: Optional[str] = None
    fnrkAccountId: Optional[str] = None
    ckycCompliance: Optional[bool] = None
    maskedAccNumber: Optional[str] = None

    class Config:
        extra = "allow"  # tolerate bank-specific extras
