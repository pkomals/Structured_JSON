import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

NumberLike = Union[float, str]

DATE_FORMATS = (
    "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %b %Y", "%d %b '%y", "%d/%m/%y",
)
DATETIME_FORMATS = (
    "%d/%m/%Y %H:%M",
    "%d-%m-%Y %H:%M",
    "%d %b %Y %H:%M",
    "%d-%b-%Y %H:%M",
    "%Y-%m-%d %H:%M",
)

# -----------------------
# Helpers
# -----------------------

def _clean(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = s.strip()
    return s if s else None

def _to_float_or_str(v: Optional[str]) -> Optional[NumberLike]:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    # remove currency symbols and commas for parsing
    s_num = re.sub(r"[₹$,]", "", s).replace(" ", "")
    try:
        return float(s_num)
    except Exception:
        return s  # keep original string if not parseable

def _to_epoch_ms(date_str: str) -> Optional[int]:
    s = (date_str or "").strip().replace("’", "'")
    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except Exception:
            continue
    return None

def _to_epoch_ms_dt(dt_str: str) -> Optional[int]:
    s = (dt_str or "").strip().replace("’", "'")
    # try date+time formats first
    for fmt in DATETIME_FORMATS:
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except Exception:
            continue
    # then plain dates
    return _to_epoch_ms(s)

def _days_between(opening_date_str: Optional[str]) -> Optional[int]:
    if not opening_date_str:
        return None
    ts = _to_epoch_ms(opening_date_str)
    if ts is None:
        return None
    opened = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).date()
    today = datetime.now(timezone.utc).date()
    return (today - opened).days

def _find_first(rx: str, text: str, flags=re.IGNORECASE) -> Optional[str]:
    m = re.search(rx, text, flags)
    return _clean(m.group(1)) if m else None


# -----------------------
# SummaryExtractor
# -----------------------

class SummaryExtractor:
    """
    Extracts account summary fields from the first pages of a bank statement.
    - Works with label variants
    - Has fallbacks for masked values and unlabelled snippets
    - Accepts 'hints' from upstream (e.g., profile maskedAccNumber/fipId) to fill gaps
    """

    # Common label variants
    TYPE_L = r"(?:Account\s*Type|A/c\s*Type|A\.?C\.?\s*Type|Type)"
    FIPNAME_L = r"(?:Bank\s*Name|Bank|FIP\s*Name)"
    FIPID_L = r"(?:FIP\s*ID|FIPID|FIP)"
    BRANCH_L = r"(?:Branch|Branch\s*Name)"
    STATUS_L = r"(?:Status|Account\s*Status)"
    CURR_L = r"(?:Currency|Curr\.)"
    FACILITY_L = r"(?:Facility|Facility\s*Granted)"
    IFSC_L = r"(?:IFSC|IFSC\s*Code)"
    MICR_L = r"(?:MICR|MICR\s*Code)"
    OPENING_L = r"(?:Opening\s*Date|A/c\s*Opening\s*Date|Account\s*Opening\s*Date)"
    DRAWING_L = r"(?:Drawing\s*Limit|OD\s*Limit|Overdraft\s*Limit)"
    CBAL_L = r"(?:Current\s*Balance|Clr\s*Balance|Available\s*Balance)"
    ODLIM_L = r"(?:Current\s*OD\s*Limit|OD\s*Limit)"
    PENDING_AMT_L = r"(?:Pending\s*Amount|Pending\s*Amt)"
    PENDING_TYPE_L = r"(?:Pending\s*Transaction\s*Type|Pending\s*Txn\s*Type)"
    BAL_DT_L = r"(?:Balance\s*as\s*on|Balance\s*Date(?:\s*Time)?)"
    MASKED_ACCNO_L = r"(?:Account\s*Number|A/c\s*No\.?|A/C\s*No\.?)"

    IFSC_RE = r"\b([A-Z]{4}0[0-9A-Z]{6})\b"
    MICR_RE = r"\b(\d{9})\b"
    MASKED_RE = r"([Xx\*]{4,}\s*\d{3,})"

    def __init__(self, debug: bool = False):
        self.debug = debug
        self.summary_keywords = {
            "branch": ["branch"],
            "currency": ["currency", "crn"],
            "ifscCode": ["ifsc code", "ifsc"],
            "micrCode": ["micr code", "micr"],
        }

    def extract(self, raw_pages: List[Dict[str, Any]], hints: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        raw_pages: output of PDFTextExtractor.extractor()
        hints: optional dict, e.g., {"maskedAccNumber": "...", "fipId": "...", "fipName": "..."}
        """
        hints = hints or {}
        pages_text = "\n".join(p.get("text") or "" for p in raw_pages[:2])

        # --- direct labeled captures ---
        out: Dict[str, Any] = {
            "type": _find_first(self.TYPE_L + r"\s*[:\-]\s*([A-Za-z ]+)", pages_text),
            "fipId": _find_first(self.FIPID_L + r"\s*[:\-]\s*([^\n]+)", pages_text),
            "branch": _find_first(self.BRANCH_L + r"\s*[:\-]\s*([^\n]+)", pages_text),
            "status": _find_first(self.STATUS_L + r"\s*[:\-]\s*([A-Za-z ]+)", pages_text),
            "fipName": _find_first(self.FIPNAME_L + r"\s*[:\-]\s*([^\n]+)", pages_text),
            "currency": _find_first(self.CURR_L + r"\s*[:\-]\s*([A-Za-z]{3})", pages_text),
            "facility": _find_first(self.FACILITY_L + r"\s*[:\-]\s*([^\n]+)", pages_text),
            "ifscCode": None,
            "micrCode": None,
            "exchgeRate": _to_float_or_str(_find_first(r"(?:Exchange\s*Rate|Exch\.*\s*Rate)\s*[:\-]\s*([^\n]+)", pages_text)),
            "openingDate": _find_first(self.OPENING_L + r"\s*[:\-]\s*([0-9A-Za-z/\-'\s]+)", pages_text),
            "account_type": None,  # high-level category (e.g., deposit); often same as 'type', leave for normalizer if needed
            "drawingLimit": _to_float_or_str(_find_first(self.DRAWING_L + r"\s*[:\-]\s*([^\n]+)", pages_text)),
            "linkedAccRef": _find_first(r"(?:Linked\s*Acc(?:ount)?\s*Ref|Linked\s*Ref)\s*[:\-]\s*([^\n]+)", pages_text),
            "fnrkAccountId": _find_first(r"(?:FNRK\s*Account\s*Id|FNRK\s*ID)\s*[:\-]\s*([^\n]+)", pages_text),
            "currentBalance": _to_float_or_str(_find_first(self.CBAL_L + r"\s*[:\-]\s*([^\n]+)", pages_text)),
            "currentODLimit": _to_float_or_str(_find_first(self.ODLIM_L + r"\s*[:\-]\s*([^\n]+)", pages_text)),
            "pending_amount": _to_float_or_str(_find_first(self.PENDING_AMT_L + r"\s*[:\-]\s*([^\n]+)", pages_text)),
            "balanceDateTime": None,
            "maskedAccNumber": None,
            "accountAgeInDays": None,
            "pending_transactionType": _find_first(self.PENDING_TYPE_L + r"\s*[:\-]\s*([^\n]+)", pages_text),
        }

        

        # IFSC / MICR: try strict patterns anywhere if not labeled
        out["ifscCode"] = _find_first(self.IFSC_L + r"\s*[:\-]\s*(" + self.IFSC_RE + r")", pages_text) or _find_first(self.IFSC_RE, pages_text, flags=0)
        out["micrCode"] = _find_first(self.MICR_L + r"\s*[:\-]\s*(" + self.MICR_RE + r")", pages_text) or _find_first(self.MICR_RE, pages_text, flags=0)

        # Opening date normalize (keep as string per schema)
        if out["openingDate"]:
            out["openingDate"] = out["openingDate"].replace("  ", " ").strip()

        # balance "as on" datetime (date or date+time)
        bal_dt = _find_first(self.BAL_DT_L + r"\s*[:\-]?\s*([0-9A-Za-z/\-'\s:]+)", pages_text)
        if bal_dt:
            out["balanceDateTime"] = _to_epoch_ms_dt(bal_dt)

        # masked account number
        masked_label = _find_first(self.MASKED_ACCNO_L + r"\s*[:\-]\s*([^\n]+)", pages_text)
        if masked_label:
            m = re.search(r"([Xx\*]{4,}\s*\d{3,}|[Xx\*]+[\d]+)", masked_label)
            out["maskedAccNumber"] = _clean(m.group(1)) if m else _clean(masked_label)
        else:
            m2 = re.search(r"([Xx\*]{4,}\s*\d{3,})", pages_text)
            if m2:
                out["maskedAccNumber"] = _clean(m2.group(1))

        # Fill hints for gaps
        for k in ("maskedAccNumber", "fipId", "fipName"):
            if not out.get(k) and hints.get(k):
                out[k] = hints[k]

        # infer currency if amounts printed with currency glyph
        if not out["currency"] and re.search(r"[₹]", pages_text):
            out["currency"] = "INR"

        # optional: compute accountAgeInDays if openingDate exists
        out["accountAgeInDays"] = _days_between(out["openingDate"])

        if self.debug:
            print("\n— SummaryExtractor (preview) —")
            for k in (
                "type","fipName","fipId","branch","status","currency","facility",
                "ifscCode","micrCode","openingDate","currentBalance","drawingLimit",
                "currentODLimit","pending_amount","balanceDateTime","maskedAccNumber",
                "accountAgeInDays","pending_transactionType",
            ):
                print(f"{k:22s}: {out.get(k)}")

        # Return dict shaped for your Pydantic Summary; model will coerce where needed
        return out
