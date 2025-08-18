# src/TransactionMapper.py
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

NumberLike = Union[float, str]

DATE_FORMATS = (
    "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %b %Y", "%d %b '%y", "%d/%m/%y",
)

MODE_PATTERNS: List[Tuple[str, str]] = [
    (r"\bUPI\b|\bVPA\b|/UPI/", "UPI"),
    (r"\bIMPS\b", "IMPS"),
    (r"\bNEFT\b", "NEFT"),
    (r"\bRTGS\b", "RTGS"),
    (r"\bACH\b|\bNACH\b", "ACH"),
    (r"\bATM\b|ATM\s*WDL|CASH\s*WDL", "ATM"),
    (r"\bPOS\b|CARD|DEBIT\s*CARD|CREDIT\s*CARD|ECOM|EPOS|SWIPE", "CARD"),
    (r"\bCHQ\b|CHEQUE|CHEQ", "CHEQUE"),
    (r"NET\s*BANKING|INTERNET\s*BANKING|IB\s*TRF", "NETBANKING"),
    (r"\bINTEREST\b|INT\.?\s*CR", "INTEREST"),
    (r"\bCHARGES\b|FEE|GST|REV\.? CHG", "CHARGES"),
]

TXN_ID_RE = re.compile(
    r"\b([A-Z]{2,}\d{6,}|[A-Z0-9]{8,}|\d{9,})\b"
)  # loose; catches NEFT/IMPS/UPI ids etc.

REF_HINTS = re.compile(r"\b(Ref(?:erence)?|RRN|UTR|Txn\s*Id|Order\s*Id|Cheque\s*No\.?)\b", re.I)

def _clean(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = s.strip()
    return s if s else None

def _to_float_or_none(v: Any) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    s = (
        s.replace(",", "")
        .replace("₹", "")
        .replace("$", "")
        .replace("INR", "")
        .replace("CR", "")
        .replace("DR", "")
        .replace("+", "")
        .strip()
    )
    try:
        return float(s)
    except Exception:
        return None

def _date_to_epoch_ms(s: Optional[str]) -> Optional[int]:
    if not s:
        return None
    s = s.strip().replace("’", "'")
    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except Exception:
            continue
    return None

def _infer_mode(narr: str) -> str:
    for rx, label in MODE_PATTERNS:
        if re.search(rx, narr, re.I):
            return label
    return "OTHER"

def _pick_reference(description: str, ref_field: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Try to extract txn id and/or reference from narration + ref column.
    """
    candidate = None
    if ref_field and (REF_HINTS.search(ref_field) or TXN_ID_RE.search(ref_field)):
        candidate = _clean(ref_field)

    # try narration too
    m = TXN_ID_RE.search(description)
    if m:
        txn_id = m.group(1)
    else:
        txn_id = None

    return txn_id, candidate

def _infer_type_and_amount(row: Dict[str, Any]) -> Tuple[Optional[str], Optional[float]]:
    """
    Decide CREDIT/DEBIT and the amount using flexible inputs:
    - debit / credit columns
    - single 'amount' column + 'type' column (Debit/Credit)
    - signed amount
    """
    debit = _to_float_or_none(row.get("debit"))
    credit = _to_float_or_none(row.get("credit"))
    amount = _to_float_or_none(row.get("amount"))
    kind = _clean(row.get("type"))

    if debit and not credit:
        return "DEBIT", debit
    if credit and not debit:
        return "CREDIT", credit

    if amount is not None and kind:
        if kind.lower().startswith("cr"):
            return "CREDIT", amount
        if kind.lower().startswith("dr") or kind.lower().startswith("debit"):
            return "DEBIT", amount

    # signed amount in 'amount'?
    if isinstance(row.get("amount"), str):
        s = row["amount"].strip()
        if s.startswith("-"):
            return "DEBIT", _to_float_or_none(s)
        if s.startswith("+"):
            return "CREDIT", _to_float_or_none(s)

    # last resort: if only amount present with no hint, leave type None
    return None, amount


class TransactionMapper:
    """
    Map HeaderBasedTableParser rows -> your transaction schema.
    Context allows passing maskedAccNumber/fipId/account_type to stamp into each record.
    """

    def __init__(self, default_account_type: Optional[str] = None):
        self.default_account_type = default_account_type

    def map(
        self,
        raw_rows: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        raw_rows: list of dicts produced by HeaderBasedTableParser, e.g.
            {"txn_date": "01/06/2018", "value_date": "01/06/2018",
             "description": "UPI/AMAZON PAY/AXI123", "ref": "UTR1234",
             "debit": "", "credit": "250.00", "balance": "1200.50" }

        context: dict with optional keys to stamp:
            {"maskedAccNumber": "...", "fipId": "...", "linkedAccRef": "...",
             "fnrkAccountId": "...", "account_type": "deposit"}
        """
        ctx = context or {}
        out: List[Dict[str, Any]] = []

        for r in raw_rows or []:
            desc = _clean(r.get("description")) or ""
            ref_field = _clean(r.get("ref"))
            value_date = _clean(r.get("value_date")) or _clean(r.get("txn_date"))
            bal = _to_float_or_none(r.get("balance"))

            txn_type, amt = _infer_type_and_amount(r)
            mode = _infer_mode(desc) if desc else "OTHER"
            txn_id, reference = _pick_reference(desc, ref_field)

            item: Dict[str, Any] = {
                "mode": mode,
                "type": txn_type,  # "CREDIT" / "DEBIT" / None
                "fipId": ctx.get("fipId"),
                "txnId": txn_id,
                "amount": amt,  # float or None (schema allows number|string|null; we keep float)
                "narration": desc or None,
                "reference": reference,
                "valueDate": _date_to_epoch_ms(value_date),
                "account_type": ctx.get("account_type") or self.default_account_type,
                "linkedAccRef": ctx.get("linkedAccRef"),
                "fnrkAccountId": ctx.get("fnrkAccountId"),
                "currentBalance": bal,
                "maskedAccNumber": ctx.get("maskedAccNumber"),
                "transactionTimestamp": _date_to_epoch_ms(_clean(r.get("txn_date")) or value_date),
            }

            # If everything important is missing, skip row
            if not any([item["amount"], item["narration"], item["txnId"]]):
                continue

            out.append(item)

        return out
