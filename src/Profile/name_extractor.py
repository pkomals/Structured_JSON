# src/fields/name_extractor.py
from __future__ import annotations
from typing import List, Dict, Any, Optional, Tuple
import re

# --- helpers ---------------------------------------------------------------

HEADERISH = re.compile(
    r"(statement|account\b(?!\s*holder)|summary|period|balance|branch|ifsc|micr|"
    r"page\s+\d+|search|relationship|customer\s*id|cust\s*id|"
    r"transaction|cheque|remarks|amount|date|from|to|type|list|"
    r"email\s*id|phone\s*no|mobile\s*no|contact)",   # add common side labels
    re.I,
)
NEG_NAME_TERMS = {
    # table/labels that must NOT be treated as a person’s name
    "nominee", "joint holder", "joint-holder", "joint  holder",
    "guardian", "relationship manager", "rm", "rm name",
    "email", "email id", "phone", "phone no", "mobile", "contact",
    "branch", "ifsc", "micr", "crn", "currency", "statement", "search",
    "account number", "account no", "customer id", "cust id", "summary","bank","app","file","digital"
}

import re

_NAME_AFTER_ACCOUNT_BLOCK = re.compile(
    r"""               # look for
    account \s* (?:number|no) \b   # "Account Number"
    [^\S\r\n]* \r?\n               # then a newline
    [^\n]* \)                      # a line containing the closing ) of "(INR)" etc.
    \s* [-–—:] \s*                 # a dash/colon separator with spaces
    (?P<who>[A-Za-z][A-Za-z\s\.'/,-]{3,})   # capture the name-ish tail
    (?:\r?\n|$)                    # end of that line
    """,
    re.IGNORECASE | re.VERBOSE,
)
_CORPORATE = re.compile(r"\b(bank|limited|ltd|pvt|plc|finance|services|co\.?)\b", re.I)
_HEADERISH = re.compile(r"(statement|transaction|date\s+from|page\s+\d+|summary|search)", re.I)

def _sanitize_name(raw: str) -> str | None:
    # normalize slashes → space, collapse whitespace
    s = re.sub(r"\s*/\s*", " ", raw)
    s = " ".join(s.split())
    # strip common honorifics
    s = re.sub(r"^(mr|mrs|ms|shri|smt|dr|prof)\.?\s+", "", s, flags=re.I)
    # quick guards
    if any(ch.isdigit() for ch in s): return None
    if _CORPORATE.search(s) or _HEADERISH.search(s): return None
    toks = s.split()
    if not (2 <= len(toks) <= 6): return None
    # Title‑case if screaming caps
    return s.title() if s.isupper() else s

CORPORATE = re.compile(r"\b(bank|finance|limited|ltd|pvt|plc|nbfc|branch|india)\b", re.I)
RMISH = re.compile(r"\bRM\b|\bRelationship\s*Manager\b", re.I)

NAME_TOKEN = r"[A-Za-z][A-Za-z\.\-']*"
NAME_LINE_RE = re.compile(rf"^{NAME_TOKEN}(?:\s+{NAME_TOKEN}){{1,4}}$", re.U)

PREFIXES = re.compile(r"^(mr|mrs|ms|shri|smt|dr|prof)\.?\s+", re.I)

def _clean(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = " ".join(s.replace("cid:9", " ").split())
    return s if s else None

def _title_if_caps(s: str) -> str:
    return s.title() if s.isupper() else s

def _strip_prefixes(s: str) -> str:
    return PREFIXES.sub("", s).strip()

def _is_headerish(line: str) -> bool:
    return bool(HEADERISH.search(line))

def _looks_like_name(line: str) -> bool:
    line = (line or "").strip()
    if not line or ":" in line or any(ch.isdigit() for ch in line):
        return False
    # reject if any negative term is present
    low = line.lower()
    for t in NEG_NAME_TERMS:
        if t in low:
            return False
    if _is_headerish(line):
        return False
    if RMISH.search(line) or CORPORATE.search(line):
        return False
    # allow 2–5 tokens of alphabetic-ish words
    if NAME_LINE_RE.match(line):
        return True
    tokens = line.split()
    return 2 <= len(tokens) <= 5 and all(re.match(r"^[A-Za-z\.\-']+$", t) for t in tokens)

def _lines(raw_pages: List[Dict[str, Any]], first_n_pages: int = 2) -> List[str]:
    txt = "\n".join(p.get("text", "") or "" for p in raw_pages[:first_n_pages])
    return [_clean(ln) or "" for ln in txt.splitlines()]

def _find_zone(lines: List[str], title_pat: re.Pattern) -> Tuple[int, int]:
    for i, ln in enumerate(lines):
        if title_pat.search(ln or ""):
            j = i + 1
            while j < len(lines):
                nxt = lines[j] or ""
                if not nxt.strip() or _is_headerish(nxt):
                    break
                j += 1
            return i + 1, j
    return -1, -1

# --- extractor -------------------------------------------------------------

class NameExtractor:
    NAME_ADDR_TITLE = re.compile(r"\bname\s*&?\s*address\b", re.I)
    # Same-line “Account Number … ) - ANURAG SINHA” (allow various dashes)
    ACCOUNT_LINE_SAME = re.compile(
        r"account\s*(?:number|no)\b[^\n]*\)\s*[-–—:]\s*([A-Z][A-Z\s\.'-]{3,})",
        re.I,
    )
    def __init__(self, debug: bool = False):
        self.debug = debug
    
   
    def extract(self, raw_pages: List[Dict[str, Any]], tables: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
        # --- try progressively larger page windows: 1, 2, 3, 4 ---
        for window in (1, 2, 3, 4):
            result = self._extract_from_window(raw_pages, tables, window)
            if result.get("name"):
                return result

        # nothing found even after 4 pages
        return {"name": None, "confidence": 0.0, "evidence": None}

    # ---- everything below is the SAME logic you already have, but scoped per window ----
    def _extract_from_window(self, raw_pages: List[Dict[str, Any]], tables: List[Dict[str, Any]] | None, window: int) -> Dict[str, Any]:
        # build text/lines from the first `window` pages
        pages_text = "\n".join(p.get("text") or "" for p in raw_pages[:window])
        lines = (pages_text or "").splitlines()

        # 1) “Account Number ↵ … ) - NAME” (multi-line block)
        m_block = _NAME_AFTER_ACCOUNT_BLOCK.search(pages_text)
        prefilled_name = _sanitize_name(m_block.group("who")) if m_block else None

        # 2) Name & Address zone
        start, end = _find_zone(lines, self.NAME_ADDR_TITLE)
        if start != -1:
            for ln in lines[start:end][:6]:
                if _looks_like_name(ln):
                    nm = _strip_prefixes(_title_if_caps(ln))
                    return {"name": nm, "confidence": 0.95, "evidence": f"name&address zone (first {window}p)"}

        # 3) Account line — same line
        joined = "\n".join(lines)
        m = self.ACCOUNT_LINE_SAME.search(joined)
        if m:
            cand = m.group(1).strip()
            cand = re.split(r"\b(transaction|search|period|list)\b", cand, flags=re.I)[0].strip()
            tokens = [t for t in cand.split() if t.isalpha()]
            if 2 <= len(tokens) <= 5:
                nm = _strip_prefixes(_title_if_caps(" ".join(tokens)))
                if _looks_like_name(nm):
                    return {"name": nm, "confidence": 0.88, "evidence": f"account line (same line, {window}p)"}

        # 4) Account line — next line after number
        for i, ln in enumerate(lines[:60]):
            if ln and re.search(r"\baccount\s*(?:number|no)\b", ln, re.I):
                k = i + 1
                seen = 0
                while k < len(lines) and seen < 3:
                    nxt = (lines[k] or "").strip()
                    k += 1
                    if not nxt:
                        continue
                    seen += 1
                    m2 = re.search(r"\)\s*[-–—:]\s*([A-Za-z][A-Za-z\s\.'/-]{3,})$", nxt)
                    if m2:
                        cand = m2.group(1)
                        cand = re.sub(r"\s*/\s*", " ", cand)
                        cand = " ".join(cand.split())
                        cand = re.sub(r"^(mr|mrs|ms|shri|smt|dr|prof)\.?\s+", "", cand, flags=re.I)
                        toks = cand.split()
                        if (2 <= len(toks) <= 5
                            and not any(ch.isdigit() for ch in cand)
                            and not HEADERISH.search(cand)
                            and not _CORPORATE.search(cand)):
                            return {"name": cand.title() if cand.isupper() else cand,
                                    "confidence": 0.90,
                                    "evidence": f"account line (next line, {window}p)"}
                    if _looks_like_name(nxt):
                        nm = _strip_prefixes(_title_if_caps(nxt))
                        return {"name": nm, "confidence": 0.86, "evidence": f"account line (next line fallback, {window}p)"}
                break

        # 5) Top-left block heuristic
        for ln in lines[:15]:
            if _looks_like_name(ln):
                nm = _strip_prefixes(_title_if_caps(ln))
                return {"name": nm, "confidence": 0.70, "evidence": f"top-left block ({window}p)"}

        # 6) Table fallbacks
        if tables:
            for tbl in tables[:3]:
                for row in tbl.get("rows", []):
                    for i, cell in enumerate(row):
                        if isinstance(cell, str) and re.search(r"\b(account\s*holder|customer)\s*name\b", cell, re.I):
                            if re.search(r"\b(joint\s*holder|nominee)\b", cell, re.I):
                                continue
                            if i + 1 < len(row) and isinstance(row[i+1], str):
                                cand = row[i+1].strip()
                                if _looks_like_name(cand):
                                    nm = _strip_prefixes(_title_if_caps(cand))
                                    return {"name": nm, "confidence": 0.65, "evidence": f"table right cell ({window}p)"}
            for tbl in tables[:3]:
                rows = tbl.get("rows", [])
                for ri in range(len(rows) - 1):
                    row = rows[ri]
                    for ci, cell in enumerate(row):
                        if isinstance(cell, str) and re.search(r"\b(account\s*holder|customer)\s*name\b", cell, re.I):
                            if re.search(r"\b(joint\s*holder|nominee)\b", cell, re.I):
                                continue
                            below = rows[ri + 1][ci] if ci < len(rows[ri + 1]) else None
                            if isinstance(below, str) and _looks_like_name(below.strip()):
                                nm = _strip_prefixes(_title_if_caps(below.strip()))
                                return {"name": nm, "confidence": 0.62, "evidence": f"table below cell ({window}p)"}

        # 7) If we had a clean “account‑block” name and nothing else beat it, use it
        if prefilled_name:
            return {"name": prefilled_name, "confidence": 0.60, "evidence": f"account‑block pattern ({window}p)"}

        return {"name": None, "confidence": 0.0, "evidence": None}


    # def extract(self, raw_pages: List[Dict[str, Any]], tables: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    #     pages_text = "\n".join(p.get("text") or "" for p in raw_pages[:2])
    #     lines = (pages_text or "").splitlines()

    #     # --- try the specific "Account Number ↵ ... ) - NAME" shape first ---
    #     prefilled_name = None
    #     m_block = _NAME_AFTER_ACCOUNT_BLOCK.search(pages_text)
    #     if m_block:
    #         nm = _sanitize_name(m_block.group("who"))
    #         if nm:
    #             if self.debug:
    #                 print(f"[name via account-block] -> {nm!r}")
    #             # set now so later logic doesn't overwrite unless a labeled name is found
    #             prefilled_name = nm
    #         else:
    #             prefilled_name = None
    #     else:
    #         prefilled_name = None

    #     # 1) Name & Address zone (highest confidence)
    #     start, end = _find_zone(lines, self.NAME_ADDR_TITLE)
    #     if start != -1:
    #         for ln in lines[start:end][:6]:
    #             if _looks_like_name(ln):
    #                 nm = _strip_prefixes(_title_if_caps(ln))
    #                 return {"name": nm, "confidence": 0.95, "evidence": "name&address zone"}

    #     # 2) Account Number → Name
    #     # 2a) Same-line variant: “… (INR) - NAME”
    #     joined = "\n".join(lines)
    #     m = self.ACCOUNT_LINE_SAME.search(joined)
        
    #     if m:
    #         cand = m.group(1).strip()
    #         # stop at common UI words if they leaked in
    #         cand = re.split(r"\b(transaction|search|period|list)\b", cand, flags=re.I)[0].strip()
    #         tokens = [t for t in cand.split() if t.isalpha()]
    #         if 2 <= len(tokens) <= 5:
    #             nm = _strip_prefixes(_title_if_caps(" ".join(tokens)))
    #             if _looks_like_name(nm):
    #                 return {"name": nm, "confidence": 0.88, "evidence": "account line (same line)"}

    #     # 2b) Next-line variant: number on its own line, then ") - NAME"
    #     for i, ln in enumerate(lines[:60]):
    #             if ln and re.search(r"\baccount\s*(?:number|no)\b", ln, re.I):
    #                 k = i + 1
    #                 seen = 0
    #                 while k < len(lines) and seen < 3:
    #                     nxt = (lines[k] or "").strip()
    #                     k += 1
    #                     if not nxt:
    #                         continue
    #                     seen += 1

    #                     # try to carve name from "... ) - NAME" (allow weird dashes/spaces)
    #                     m = re.search(r"\)\s*[-–—:]\s*([A-Za-z][A-Za-z\s\.'/-]{3,})$", nxt)
    #                     if m:
    #                         cand = m.group(1)
    #                         # normalize: remove slashes, compact spaces, strip honorifics
    #                         cand = re.sub(r"\s*/\s*", " ", cand)
    #                         cand = " ".join(cand.split())
    #                         cand = re.sub(r"^(mr|mrs|ms|shri|smt|dr|prof)\.?\s+", "", cand, flags=re.I)

    #                         # final sanity: must not look like UI/corporate, 2–5 tokens, no digits
    #                         toks = cand.split()
    #                         if (2 <= len(toks) <= 5
    #                             and not any(ch.isdigit() for ch in cand)
    #                             and not HEADERISH.search(cand)
    #                             and not CORPORATE.search(cand)):
    #                             return {"name": cand.title() if cand.isupper() else cand,
    #                                     "confidence": 0.9,
    #                                     "evidence": "account line (number→name on next line)"}

    #                     # if the whole line already looks like a clean name (rare), accept
    #                     if _looks_like_name(nxt):
    #                         nm = _strip_prefixes(_title_if_caps(nxt))
    #                         return {"name": nm, "confidence": 0.86, "evidence": "account line (next line)"}
    #                 break


    #     # 3) Top-left block heuristic (much stricter now)
    #     for ln in lines[:15]:
    #         if _looks_like_name(ln):
    #             nm = _strip_prefixes(_title_if_caps(ln))
    #             return {"name": nm, "confidence": 0.70, "evidence": "top-left block"}

    #     # 4) Table fallback (rare)
    #     if tables:
    #         # right cell
    #         for tbl in tables[:3]:
    #             for row in tbl.get("rows", []):
    #                 for i, cell in enumerate(row):
    #                     if isinstance(cell, str) and re.search(r"\b(account\s*holder|customer)\s*name\b", cell, re.I):
    #                         if i + 1 < len(row) and isinstance(row[i+1], str):
    #                             cand = row[i+1].strip()
    #                             if _looks_like_name(cand):
    #                                 nm = _strip_prefixes(_title_if_caps(cand))
    #                                 return {"name": nm, "confidence": 0.65, "evidence": "table right cell"}
    #         # below cell
    #         for tbl in tables[:3]:
    #             rows = tbl.get("rows", [])
    #             for ri in range(len(rows) - 1):
    #                 row = rows[ri]
    #                 for ci, cell in enumerate(row):
    #                     if isinstance(cell, str) and re.search(r"\b(account\s*holder|customer)\s*name\b", cell, re.I):
    #                         below = rows[ri + 1][ci] if ci < len(rows[ri + 1]) else None
    #                         if isinstance(below, str) and _looks_like_name(below.strip()):
    #                             nm = _strip_prefixes(_title_if_caps(below.strip()))
    #                             return {"name": nm, "confidence": 0.62, "evidence": "table below cell"}
    #     if prefilled_name:
    #         return {"name": prefilled_name, "confidence": 0.80, "evidence": "account-block fallback"}

        # return {"name": None, "confidence": 0.0, "evidence": None}
