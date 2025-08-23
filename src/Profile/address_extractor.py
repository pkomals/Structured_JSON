# # src/fields/address_extractor.py
# from __future__ import annotations
# from typing import List, Dict, Any, Optional
# from collections import deque
# import re

# # --- regexes / signals ------------------------------------------------------

# CITIES_HINT = r"(?:mumbai|delhi|new\s*delhi|bengaluru|bangalore|chennai|kolkata|pune|hyderabad|gurgaon|noida|ahmedabad|jaipur|indore|surat|vadodara|thane|navi\s*mumbai)"
# PIN_RE = re.compile(r"\b\d{6}\b")
# COORD_RE = re.compile(r"^\s*\d{1,3}\.\d+\s*,\s*\d{1,3}\.\d+\s*$")  # e.g., 221.0, 0.0

# AMOUNT_RE = re.compile(r"(?:^|[\s:])\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?(?:\s*(?:cr|dr)\.?)?\b", re.I)
# DATE_RE   = re.compile(r"\b(?:\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|[A-Za-z]{3}\s+\d{1,2},?\s+\d{4})\b")
# CRDR_RE   = re.compile(r"\b(?:cr|dr)\b", re.I)

# # Common transaction / channel codes + merchants that must be excluded
# TRANS_CODE_RE = re.compile(
#     r"\b(?:BIL/ONL|NEFT|IMPS|UPI|ACH|NACH|ATM|POS|ECS|RTGS|CHEQ|CHQ|CMS|CDM|CWDR|CWDL|REF|TRF|MMT|IRCTC|INDIGO)\b",
#     re.I,
# )
# MERCHANT_RE = re.compile(r"\b(amazon|flipkart|zomato|swiggy|uber|ola|paytm|phonepe|google\s*pay|gpay|airtel|vodafone|jio)\b", re.I)

# HEADER_RE = re.compile(
#     r"(statement|account\b(?!\s*holder)|summary|period|balance|branch|ifsc|micr|"
#     r"page\s+\d+|search|relationship|customer\s*id|cust\s*id|"
#     r"transactions?\s+list|transaction\s+summary|cheque|remarks|amount|date|from|to|type|payment\s+due|credit\s+limit)",
#     re.I,
# )

# ADDRESS_CUES = re.compile(
#     r"(address|mailing\s*address|communication\s*address|correspondence\s*address|"
#     r"road|rd\.|street|st\.|lane|ln\.|nagar|complex|chs|vihar|sector|block|phase|layout|"
#     r"society|apartment|apt\.|tower|villa|project|floor|flat|plot|house|near|opp\.|opposite)",
#     re.I,
# )


# def clean(s: Optional[str]) -> Optional[str]:
#     if s is None: 
#         return None
#     s = " ".join(s.replace("cid:9", " ").split())
#     return s or None

# def alpha_ratio(s: str) -> float:
#     if not s: 
#         return 0.0
#     a = sum(ch.isalpha() for ch in s)
#     return a / max(1, len(s))

# def digit_ratio(s: str) -> float:
#     if not s:
#         return 0.0
#     d = sum(ch.isdigit() for ch in s)
#     return d / max(1, len(s))

# def is_headerish(s: str) -> bool:
#     return bool(HEADER_RE.search(s))

# def is_amountish(s: str) -> bool:
#     return bool(AMOUNT_RE.search(s))

# def is_dateish(s: str) -> bool:
#     return bool(DATE_RE.search(s))

# def is_transactionish(s: str) -> bool:
#     # heavy filters for lines like "BIL/ONL/..., UPI/..., ... Cr"
#     if TRANS_CODE_RE.search(s) or MERCHANT_RE.search(s) or CRDR_RE.search(s):
#         return True
#     if s.count("/") >= 2:
#         return True
#     return False

# def likely_address_line(s: str) -> bool:
#     s = s.strip()
#     if not s:
#         return False
#     if COORD_RE.match(s):            # e.g., "221.0, 0.0"
#         return False
#     if is_headerish(s) or is_amountish(s) or is_dateish(s) or is_transactionish(s):
#         return False
#     # Require address cues OR (city/pin + reasonable text)
#     cues = ADDRESS_CUES.search(s) or re.search(CITIES_HINT, s, re.I) or PIN_RE.search(s)
#     if not cues:
#         return False
#     # Avoid lines dominated by digits/symbols
#     if digit_ratio(s) > 0.4 and not PIN_RE.search(s):
#         return False
#     if alpha_ratio(s) < 0.35:
#         return False
#     return True

# def cut_after_pin(text: str) -> str:
#     """
#     Truncate at first PIN, then strip any trailing codes like '/Cr', '/Dr', amounts, etc.
#     """
#     if not text:
#         return text
#     m = PIN_RE.search(text)
#     if m:
#         text = text[: m.end()]
#     # strip trailing punctuation and obvious code tails
#     text = re.sub(r"[,\s;:/\-]+$", "", text)
#     return text

# def is_pin_only(text: str) -> bool:
#     t = (text or "").strip()
#     return bool(PIN_RE.fullmatch(t)) or (t.isdigit() and len(t) == 6)

# def flatten_lines(raw_pages: List[Dict[str, Any]], first_n_pages: int = 2) -> List[str]:
#     txt = "\n".join(p.get("text", "") or "" for p in raw_pages[:first_n_pages])
#     return [clean(ln) or "" for ln in txt.splitlines()]

# # ---------------------------------------------------------------------------

# class AddressExtractor:
#     """
#     Returns: {'address': str|None, 'confidence': float, 'evidence': str|None}
#     """
#     ADDRESS_LABELS = re.compile(r"\b(address|mailing\s*address|communication\s*address|correspondence\s*address)\b", re.I)
#     STOP_SCAN = re.compile(r"(transactions?\s+list|transaction\s+summary)", re.I)

#     def __init__(self, debug: bool = False):
#         self.debug = debug

#     # 1) labeled multi-line block
#     def _labeled_block(self, text: str) -> Optional[str]:
#         m = self.ADDRESS_LABELS.search(text)
#         if not m:
#             return None
#         start = m.end()
#         tail = text[start:].splitlines()
#         buf: list[str] = []
#         for ln in tail:
#             s = (ln or "").strip()
#             if not s: break
#             if is_headerish(s) or is_amountish(s) or is_dateish(s) or is_transactionish(s):
#                 break
#             buf.append(s)
#             if len(buf) >= 6:
#                 break
#         joined = ", ".join(buf)
#         joined = cut_after_pin(joined)
#         return joined or None

#     # 2) top-left block with backfill before PIN, only before Transactions section
#     def _top_left_block(self, lines: List[str]) -> Optional[str]:
#         buf: list[str] = []
#         recent = deque(maxlen=3)
#         started = False

#         for ln in lines[:120]:
#             if self.STOP_SCAN.search(ln):
#                 break

#             s = (ln or "").strip()
#             if not s:
#                 continue

#             if not (is_headerish(s) or is_amountish(s) or is_dateish(s) or is_transactionish(s)):
#                 recent.append(s)

#             if not started and likely_address_line(s):
#                 started = True
#                 buf.append(s)
#                 if PIN_RE.search(s):
#                     pre = [x for x in list(recent)[:-1] if likely_address_line(x)]
#                     pre = pre[-2:]
#                     buf = pre + buf
#                     break
#                 continue

#             if started:
#                 if is_headerish(s) or is_amountish(s) or is_dateish(s) or is_transactionish(s):
#                     break
#                 if likely_address_line(s):
#                     buf.append(s)
#                     if PIN_RE.search(s):
#                         pre = [x for x in list(recent) if likely_address_line(x) and x not in buf]
#                         buf = pre[-2:] + buf
#                         break
#                 else:
#                     break

#         if not buf:
#             return None
#         joined = ", ".join(buf)
#         joined = cut_after_pin(joined)
#         if is_pin_only(joined):
#             return None
#         return joined or None

#     # 3) table fallback (right/below cell of Address label)
#     def _from_tables(self, tables: List[Dict[str, Any]] | None) -> Optional[str]:
#         if not tables:
#             return None
#         for tbl in tables[:3]:
#             rows = tbl.get("rows", [])
#             # right-cell
#             for row in rows:
#                 for i, cell in enumerate(row):
#                     if not isinstance(cell, str):
#                         continue
#                     if self.ADDRESS_LABELS.search(cell):
#                         if i + 1 < len(row) and isinstance(row[i + 1], str):
#                             cand = clean(row[i + 1]) or ""
#                             if likely_address_line(cand):
#                                 return cut_after_pin(cand) or None
#             # below-cell
#             for ri in range(len(rows) - 1):
#                 row = rows[ri]
#                 for ci, cell in enumerate(row):
#                     if isinstance(cell, str) and self.ADDRESS_LABELS.search(cell):
#                         below = rows[ri + 1][ci] if ci < len(rows[ri + 1]) else None
#                         if isinstance(below, str) and likely_address_line(below):
#                             return cut_after_pin(below) or None
#         return None

#     # public
#     def extract(
#         self,
#         raw_pages: List[Dict[str, Any]],
#         tables: List[Dict[str, Any]] | None = None,
#         first_n_pages: int = 2,
#     ) -> Dict[str, Any]:
#         text = "\n".join(p.get("text", "") or "" for p in raw_pages[:first_n_pages])
#         lines = flatten_lines(raw_pages, first_n_pages=first_n_pages)

#         # 1) Labeled block
#         addr = self._labeled_block(text)
#         if addr and not is_pin_only(addr):
#             if self.debug: print("[address] via labeled block ->", addr)
#             return {"address": addr, "confidence": 0.92, "evidence": "labeled block"}

#         # 2) Top-left block (before transactions)
#         addr = self._top_left_block(lines)
#         if addr and not is_pin_only(addr):
#             if self.debug: print("[address] via top-left block ->", addr)
#             return {"address": addr, "confidence": 0.82, "evidence": "top-left block"}

#         # 3) Tables
#         addr = self._from_tables(tables)
#         if addr and not is_pin_only(addr):
#             if self.debug: print("[address] via tables ->", addr)
#             return {"address": addr, "confidence": 0.70, "evidence": "table right/below cell"}

#         if self.debug: print("[address] not found")
#         return {"address": None, "confidence": 0.0, "evidence": None}

# src/fields/address_extractor.py
from __future__ import annotations
from typing import List, Dict, Any, Optional
from collections import deque
import re

# --- regexes / signals ------------------------------------------------------

CITIES_HINT = r"(?:mumbai|delhi|new\s*delhi|bengaluru|bangalore|chennai|kolkata|pune|hyderabad|gurgaon|noida|ahmedabad|jaipur|indore|surat|vadodara|thane|navi\s*mumbai)"
PIN_RE = re.compile(r"\b\d{6}\b")
COORD_RE = re.compile(r"^\s*\d{1,3}\.\d+\s*,\s*\d{1,3}\.\d+\s*$")  # e.g., 221.0, 0.0

AMOUNT_RE = re.compile(r"(?:^|[\s:])\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?(?:\s*(?:cr|dr)\.?)?\b", re.I)
DATE_RE = re.compile(r"\b(?:\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|[A-Za-z]{3}\s+\d{1,2},?\s+\d{4}|FY\s*\d{4}\s*-?\s*\d{2,4})\b", re.I)
CRDR_RE   = re.compile(r"\b(?:cr|dr)\b", re.I)

# Common transaction / channel codes + merchants that must be excluded
TRANS_CODE_RE = re.compile(
    r"\b(?:BIL/ONL|NEFT|IMPS|UPI|ACH|NACH|ATM|POS|ECS|RTGS|CHEQ|CHQ|CMS|CDM|CWDR|CWDL|REF|TRF|MMT|IRCTC|INDIGO)\b",
    re.I,
)
MERCHANT_RE = re.compile(r"\b(amazon|flipkart|zomato|swiggy|uber|ola|paytm|phonepe|google\s*pay|gpay|airtel|vodafone|jio)\b", re.I)

HEADER_RE = re.compile(
    r"(statement|account\b(?!\s*holder)|summary|period|balance|branch|ifsc|micr|"
    r"page\s+\d+|search|relationship|customer\s*id|cust\s*id|"
    r"transactions?\s+list|transaction\s+summary|cheque|remarks|amount|date|from|to|type|payment\s+due|credit\s+limit)",
    re.I,
)

ADDRESS_CUES = re.compile(
    r"(address|mailing\s*address|communication\s*address|correspondence\s*address|"
    r"road|rd\.|street|st\.|lane|ln\.|nagar|complex|chs|vihar|sector|block|phase|layout|"
    r"society|apartment|apt\.|tower|villa|project|residency|floor|flat|plot|house|near|opp\.|opposite)",
    re.I,
)

# Bank-related keywords that indicate bank address rather than customer address
BANK_KEYWORDS = re.compile(
    r"\b(branch|ifsc|micr|bank|head\s*office|regional\s*office|zonal\s*office|"
    r"corporate\s*office|main\s*branch|service\s*center)\b", re.I
)

def is_financial_year(s: str) -> bool:
    """Check if the line is a financial year pattern"""
    return bool(re.search(r"\bFY\s*\d{4}\s*-?\s*\d{2,4}\b", s, re.I))


def clean(s: Optional[str]) -> Optional[str]:
    if s is None: 
        return None
    s = " ".join(s.replace("cid:9", " ").split())
    return s or None

def alpha_ratio(s: str) -> float:
    if not s: 
        return 0.0
    a = sum(ch.isalpha() for ch in s)
    return a / max(1, len(s))

def digit_ratio(s: str) -> float:
    if not s:
        return 0.0
    d = sum(ch.isdigit() for ch in s)
    return d / max(1, len(s))

def is_headerish(s: str) -> bool:
    return bool(HEADER_RE.search(s))

def is_amountish(s: str) -> bool:
    return bool(AMOUNT_RE.search(s))

def is_dateish(s: str) -> bool:
    return bool(DATE_RE.search(s))

def is_transactionish(s: str) -> bool:
    # heavy filters for lines like "BIL/ONL/..., UPI/..., ... Cr"
    if TRANS_CODE_RE.search(s) or MERCHANT_RE.search(s) or CRDR_RE.search(s):
        return True
    if s.count("/") >= 2:
        return True
    return False

def is_bank_related(s: str) -> bool:
    """Check if the line contains bank-related keywords"""
    return bool(BANK_KEYWORDS.search(s))

def likely_address_line(s: str) -> bool:
    s = s.strip()
    if not s:
        return False
    if COORD_RE.match(s):            # e.g., "221.0, 0.0"
        return False
    if (is_headerish(s) or is_amountish(s) or is_dateish(s) or 
        is_transactionish(s) or is_financial_year(s)):  # Add this check
        return False
    # Require address cues OR (city/pin + reasonable text)
    cues = ADDRESS_CUES.search(s) or re.search(CITIES_HINT, s, re.I) or PIN_RE.search(s)
    if not cues:
        return False
    # Avoid lines dominated by digits/symbols
    if digit_ratio(s) > 0.4 and not PIN_RE.search(s):
        return False
    if alpha_ratio(s) < 0.35:
        return False
    return True

def cut_after_pin(text: str) -> str:
    """
    Truncate at first PIN, then strip any trailing codes like '/Cr', '/Dr', amounts, etc.
    """
    if not text:
        return text
    m = PIN_RE.search(text)
    if m:
        text = text[: m.end()]
    # strip trailing punctuation and obvious code tails
    text = re.sub(r"[,\s;:/\-]+$", "", text)
    return text

def is_pin_only(text: str) -> bool:
    t = (text or "").strip()
    return bool(PIN_RE.fullmatch(t)) or (t.isdigit() and len(t) == 6)

def flatten_lines(raw_pages: List[Dict[str, Any]], first_n_pages: int = 2) -> List[str]:
    txt = "\n".join(p.get("text", "") or "" for p in raw_pages[:first_n_pages])
    return [clean(ln) or "" for ln in txt.splitlines()]

# ---------------------------------------------------------------------------

class AddressExtractor:
    """
    Returns: {'address': str|None, 'confidence': float, 'evidence': str|None}
    """
    ADDRESS_LABELS = re.compile(r"\b(address|mailing\s*address|communication\s*address|correspondence\s*address)\b", re.I)
    CUSTOMER_LABELS = re.compile(r"\b(name\s*&?\s*address|customer\s*address|cust\s*address)\b", re.I)
    STOP_SCAN = re.compile(r"(transactions?\s+list|transaction\s+summary)", re.I)

    def __init__(self, debug: bool = False):
        self.debug = debug

    def _is_likely_bank_address_context(self, text_before: str, text_after: str) -> bool:
        """
        Check if the address label appears in a bank address context
        by looking at surrounding text
        """
        context = (text_before + " " + text_after).lower()
        
        # Check for bank-related keywords in context
        if BANK_KEYWORDS.search(context):
            return True
            
        # Check for branch-related patterns
        if re.search(r"branch\s*(?:id|code|name)", context, re.I):
            return True
            
        # Check if it's in a structured bank info section
        if re.search(r"(ifsc|micr|branch)\s*:", context, re.I):
            return True
            
        return False

    # 1) labeled multi-line block with improved context awareness
    def _labeled_block(self, text: str) -> Optional[str]:
        # First try to find customer-specific address labels
        m = self.CUSTOMER_LABELS.search(text)
        if m:
            start = m.end()
            tail = text[start:].splitlines()
            buf: list[str] = []
            for ln in tail:
                s = (ln or "").strip()
                if not s: break
                if is_headerish(s) or is_amountish(s) or is_dateish(s) or is_transactionish(s):
                    break
                buf.append(s)
                if len(buf) >= 6:
                    break
            joined = ", ".join(buf)
            joined = cut_after_pin(joined)
            if joined and not is_pin_only(joined):
                return joined

        # Then try general address labels but with context checking
        for match in self.ADDRESS_LABELS.finditer(text):
            start_pos = match.start()
            end_pos = match.end()
            
            # Get context around the match
            context_start = max(0, start_pos - 200)
            context_end = min(len(text), end_pos + 100)
            text_before = text[context_start:start_pos]
            text_after = text[end_pos:context_end]
            
            # Skip if it's likely a bank address
            if self._is_likely_bank_address_context(text_before, text_after):
                continue
            
            tail = text[end_pos:].splitlines()
            buf: list[str] = []
            for ln in tail:
                s = (ln or "").strip()
                if not s: break
                if is_headerish(s) or is_amountish(s) or is_dateish(s) or is_transactionish(s):
                    break
                # Skip if this line itself seems bank-related
                if is_bank_related(s):
                    break
                buf.append(s)
                if len(buf) >= 6:
                    break
            
            joined = ", ".join(buf)
            joined = cut_after_pin(joined)
            if joined and not is_pin_only(joined):
                return joined
                
        return None

    # 2) Enhanced top-left block with customer context prioritization
    def _top_left_block(self, lines: List[str]) -> Optional[str]:
        buf: list[str] = []
        recent = deque(maxlen=3)
        started = False
        customer_context_found = False

        for i, ln in enumerate(lines[:120]):
            if self.STOP_SCAN.search(ln):
                break

            s = (ln or "").strip()
            if not s:
                continue

            # Check if we're in a customer section
            if re.search(r"\b(customer|cust|name)\b", s, re.I) and not is_bank_related(s):
                customer_context_found = True

            # Skip lines that seem bank-related unless we're clearly in customer context
            if is_bank_related(s) and not customer_context_found:
                continue

            if not (is_headerish(s) or is_amountish(s) or is_dateish(s) or is_transactionish(s)):
                recent.append(s)

            if not started and likely_address_line(s) and not is_bank_related(s):
                started = True
                buf.append(s)
                if PIN_RE.search(s):
                    pre = [x for x in list(recent)[:-1] if likely_address_line(x) and not is_bank_related(x)]
                    pre = pre[-2:]
                    buf = pre + buf
                    break
                continue

            if started:
                if is_headerish(s) or is_amountish(s) or is_dateish(s) or is_transactionish(s):
                    break
                if is_bank_related(s):
                    break
                if likely_address_line(s):
                    buf.append(s)
                    if PIN_RE.search(s):
                        pre = [x for x in list(recent) if likely_address_line(x) and x not in buf and not is_bank_related(x)]
                        buf = pre[-2:] + buf
                        break
                else:
                    break

        if not buf:
            return None
        joined = ", ".join(buf)
        joined = cut_after_pin(joined)
        if is_pin_only(joined):
            return None
        return joined or None

    # 3) Enhanced table fallback with context awareness
    def _from_tables(self, tables: List[Dict[str, Any]] | None) -> Optional[str]:
        if not tables:
            return None
        for tbl in tables[:3]:
            rows = tbl.get("rows", [])
            
            # right-cell
            for row in rows:
                for i, cell in enumerate(row):
                    if not isinstance(cell, str):
                        continue
                    
                    # Check for customer-specific labels first
                    if self.CUSTOMER_LABELS.search(cell):
                        if i + 1 < len(row) and isinstance(row[i + 1], str):
                            cand = clean(row[i + 1]) or ""
                            if likely_address_line(cand) and not is_bank_related(cand):
                                return cut_after_pin(cand) or None
                    
                    # Then check general address labels with context
                    elif self.ADDRESS_LABELS.search(cell):
                        # Check surrounding cells for bank context
                        context_cells = []
                        if i > 0: context_cells.append(row[i-1])
                        if i < len(row) - 2: context_cells.append(row[i+2])
                        
                        context = " ".join(str(c) for c in context_cells if isinstance(c, str))
                        if not is_bank_related(context):
                            if i + 1 < len(row) and isinstance(row[i + 1], str):
                                cand = clean(row[i + 1]) or ""
                                if likely_address_line(cand) and not is_bank_related(cand):
                                    return cut_after_pin(cand) or None
            
            # below-cell
            for ri in range(len(rows) - 1):
                row = rows[ri]
                for ci, cell in enumerate(row):
                    if isinstance(cell, str):
                        if self.CUSTOMER_LABELS.search(cell):
                            below = rows[ri + 1][ci] if ci < len(rows[ri + 1]) else None
                            if isinstance(below, str) and likely_address_line(below) and not is_bank_related(below):
                                return cut_after_pin(below) or None
                        elif self.ADDRESS_LABELS.search(cell):
                            # Check context
                            context_cells = []
                            if ci > 0: context_cells.append(row[ci-1])
                            if ci < len(row) - 1: context_cells.append(row[ci+1])
                            
                            context = " ".join(str(c) for c in context_cells if isinstance(c, str))
                            if not is_bank_related(context):
                                below = rows[ri + 1][ci] if ci < len(rows[ri + 1]) else None
                                if isinstance(below, str) and likely_address_line(below) and not is_bank_related(below):
                                    return cut_after_pin(below) or None
        return None

    # 4) New method: Two-column format handler
    def _two_column_format(self, lines: List[str]) -> Optional[str]:
        """
        Handle two-column format where customer info is on the left
        and bank info is on the right
        """
        customer_lines = []
        started_collecting = False
        
        for i, line in enumerate(lines[:50]):
            s = line.strip()
            if not s:
                continue
                
            # Look for customer name as start indicator
            if ((re.search(r"^[A-Z][a-z]+\s+[A-Z][a-z]+$", s) and not is_bank_related(s)) or  
            (re.search(r"^[A-Z][A-Z\s]+$", s) and len(s.split()) <= 4 and not is_bank_related(s))):
                started_collecting = True
                continue
                
            # Stop if we hit transactions
            if self.STOP_SCAN.search(s):
                break
                
            # If we've started and find address-like content, collect it
            if started_collecting:
                # Skip labels like "Name :" "Address :" but continue collecting
                if re.search(r"^(Name|Address|City|State)\s*:", s, re.I):
                    continue
                    
                # Stop if we hit clear bank info section
                if re.search(r"^(Branch|IFSC|MICR)", s):
                    break
                    
                # Collect likely address lines
                if (likely_address_line(s) or 
                (re.search(r"^[A-Z][A-Z0-9\s\-,/]+$", s) and not is_financial_year(s)) or
                PIN_RE.search(s)):
                    customer_lines.append(s)
                    
            # Stop after getting PIN or if we have enough lines
            if customer_lines and (PIN_RE.search(customer_lines[-1]) or len(customer_lines) >= 6):
                break
                
        if customer_lines:
            joined = ", ".join(customer_lines)
            joined = cut_after_pin(joined)
            if not is_pin_only(joined):
                return joined
                
        return None

    # public
    def extract(
        self,
        raw_pages: List[Dict[str, Any]],
        tables: List[Dict[str, Any]] | None = None,
        first_n_pages: int = 2,
    ) -> Dict[str, Any]:
        text = "\n".join(p.get("text", "") or "" for p in raw_pages[:first_n_pages])
        lines = flatten_lines(raw_pages, first_n_pages=first_n_pages)

        # 1) Two-column format (new method for your specific case)
        addr = self._two_column_format(lines)
        if addr and not is_pin_only(addr):
            if self.debug: print("[address] via two-column format ->", addr)
            return {"address": addr, "confidence": 0.88, "evidence": "two-column format"}

        # 2) Enhanced labeled block
        addr = self._labeled_block(text)
        if addr and not is_pin_only(addr):
            if self.debug: print("[address] via labeled block ->", addr)
            return {"address": addr, "confidence": 0.92, "evidence": "labeled block"}

        # 3) Enhanced top-left block
        addr = self._top_left_block(lines)
        if addr and not is_pin_only(addr):
            if self.debug: print("[address] via top-left block ->", addr)
            return {"address": addr, "confidence": 0.82, "evidence": "top-left block"}

        # 4) Enhanced tables
        addr = self._from_tables(tables)
        if addr and not is_pin_only(addr):
            if self.debug: print("[address] via tables ->", addr)
            return {"address": addr, "confidence": 0.70, "evidence": "table right/below cell"}

        if self.debug: print("[address] not found")
        return {"address": None, "confidence": 0.0, "evidence": None}