# bank_statement.py
from typing import List, Optional, Union
from pydantic import BaseModel, Field, validator


# -------------------------
# Profile
# -------------------------
class Profile(BaseModel):
    # NOTE: dob is epoch milliseconds (can be negative). Your example uses a tiny -5629;
    # we keep it as Optional[int] and do not coerce here.
    dob: Optional[int] = None
    pan: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None                 # e.g., "SINGLE", "JOINT"
    email: Optional[str] = None
    fipId: Optional[str] = None
    mobile: Optional[str] = None
    address: Optional[str] = None
    nominee: Optional[str] = None              # e.g., "REGISTERED"
    landLine: Optional[str] = None
    account_type: Optional[str] = None         # e.g., "deposit", "savings"
    linkedAccRef: Optional[str] = None
    fnrkAccountId: Optional[str] = None
    ckycCompliance: Optional[bool] = None
    maskedAccNumber: Optional[str] = None

    class Config:
        extra = "allow"  # tolerate new keys the bank may add


# -------------------------
# Summary
# -------------------------
class Summary(BaseModel):
    type: Optional[str] = None                 # e.g., "SAVINGS"
    fipId: Optional[str] = None
    branch: Optional[str] = None
    status: Optional[str] = None               # e.g., "ACTIVE"
    fipName: Optional[str] = None              # e.g., "ICICI Bank"
    currency: Optional[str] = None             # e.g., "INR"
    facility: Optional[str] = None             # e.g., "NO_FACILITY_GRANTED"
    ifscCode: Optional[str] = None
    micrCode: Optional[str] = None
    exchgeRate: Optional[Union[float, str]] = None
    openingDate: Optional[str] = None          # keep as string per your schema
    account_type: Optional[str] = None
    drawingLimit: Optional[Union[str, float]] = None
    linkedAccRef: Optional[str] = None
    fnrkAccountId: Optional[str] = None
    currentBalance: Optional[Union[str, float]] = None
    currentODLimit: Optional[Union[str, float]] = None
    pending_amount: Optional[Union[float, str]] = None
    balanceDateTime: Optional[int] = None      # epoch ms
    maskedAccNumber: Optional[str] = None
    accountAgeInDays: Optional[int] = None
    pending_transactionType: Optional[str] = None

    class Config:
        extra = "allow"

    # Optional: light numeric coercion where unions allow string/number
    @staticmethod
    def _to_num_or_str(x):
        if x is None:
            return None
        s = str(x).strip()
        if not s:
            return None
        try:
            return float(s.replace(",", ""))
        except Exception:
            return s

    @validator("exchgeRate", "drawingLimit", "currentBalance", "currentODLimit", "pending_amount", pre=True)
    def _coerce_numeric_unions(cls, v):
        return cls._to_num_or_str(v)


# -------------------------
# Transaction
# -------------------------
class Transaction(BaseModel):
    mode: Optional[str] = None                 # e.g., "OTHERS", "NEFT", "UPI"
    type: Optional[str] = None                 # e.g., "CREDIT", "DEBIT"
    fipId: Optional[str] = None
    txnId: Optional[str] = None
    amount: Optional[Union[float, str]] = None
    narration: Optional[str] = None
    reference: Optional[str] = None
    valueDate: Optional[int] = None            # epoch ms
    account_type: Optional[str] = None
    linkedAccRef: Optional[str] = None
    fnrkAccountId: Optional[str] = None
    currentBalance: Optional[Union[str, float]] = None
    maskedAccNumber: Optional[str] = None
    transactionTimestamp: Optional[int] = None # epoch ms

    class Config:
        extra = "allow"

    @staticmethod
    def _to_num_or_str(x):
        if x is None:
            return None
        s = str(x).strip()
        if not s:
            return None
        try:
            return float(s.replace(",", ""))
        except Exception:
            return s

    @validator("amount", "currentBalance", pre=True)
    def _coerce_numeric_unions(cls, v):
        return cls._to_num_or_str(v)


# -------------------------
# Transactions Meta
# -------------------------
class TransactionsMeta(BaseModel):
    fipId: Optional[str] = None
    toTimestamp: Optional[int] = None          # epoch ms
    linkedAccRef: Optional[str] = None
    fnrkAccountId: Optional[str] = None
    fromTimestamp: Optional[int] = None        # epoch ms
    maskedAccNumber: Optional[str] = None
    noOfTransactions: Optional[int] = None

    class Config:
        extra = "allow"


# -------------------------
# Top-level BankStatement
# -------------------------
class BankStatement(BaseModel):
    profile: List[Profile] = Field(default_factory=list)
    summary: Summary = Field(default_factory=Summary)
    transactions: List[Transaction] = Field(default_factory=list)
    transactionsMeta: TransactionsMeta = Field(default_factory=TransactionsMeta)

    class Config:
        # Mirror your JSON Schema's `additionalProperties: false` at the top level
        extra = "forbid"
