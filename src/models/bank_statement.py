from typing import List
from pydantic import BaseModel, Field

from .profile import Profile
from .summary import Summary
from .transaction import Transaction
from .transactions_meta import TransactionsMeta

class BankStatement(BaseModel):
    """Top-level bank-statement document for a single account."""
    profile: List[Profile] = Field(default_factory=list)
    summary: Summary = Field(default_factory=Summary)
    transactions: List[Transaction] = Field(default_factory=list)
    transactionsMeta: TransactionsMeta = Field(default_factory=TransactionsMeta)

    class Config:
        # mirror your JSON Schema's `additionalProperties: false`
        extra = "forbid"
