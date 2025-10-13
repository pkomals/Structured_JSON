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
    # table/labels that must NOT be treated as a person's name
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
    \s* [-—–:] \s*                 # a dash/colon separator with spaces
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
    # DON'T strip honorifics - keep Mr., Mrs., etc.
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

# DON'T strip prefixes - keep titles like Mr., Mrs.
PREFIXES = re.compile(r"^(mr|mrs|ms|shri|smt|dr|prof)\.?\s+", re.I)

def _clean(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = " ".join(s.replace("cid:9", " ").split())
    return s if s else None

def _title_if_caps(s: str) -> str:
    return s.title() if s.isupper() else s

def _strip_prefixes(s: str) -> str:
    # DON'T strip prefixes - return as is
    return s.strip()

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


def _is_likely_branch_context(text: str, position: int) -> bool:
    """Enhanced context detection for customer vs branch names"""
    lines = text.split('\n')
    
    # Find the line containing the position
    current_pos = 0
    line_idx = 0
    for i, line in enumerate(lines):
        if current_pos <= position <= current_pos + len(line):
            line_idx = i
            break
        current_pos += len(line) + 1
    
    # Check surrounding lines (wider context)
    context_start = max(0, line_idx - 5)
    context_end = min(len(lines), line_idx + 5)
    context_lines = lines[context_start:context_end]
    context_text = " ".join(context_lines).lower()
    
    # Strong branch indicators
    branch_indicators = [
        'branch', 'ifsc', 'micr', 'branch id', 'township', 'crossing', 
        'head office', 'regional office', 'zonal office', 'service center'
    ]
    
    # Strong customer indicators  
    customer_indicators = [
        'cust id', 'customer id', 'ckyc', 'mobile no', 'aadhar', 'address',
        'account number', 'account holder', 'customer details', 'kyc'
    ]
    
    # Immediate context (same line and adjacent lines)
    immediate_context = " ".join(lines[max(0, line_idx-1):min(len(lines), line_idx+2)]).lower()
    
    # Check for strong branch context in immediate vicinity
    if any(indicator in immediate_context for indicator in ['branch', 'ifsc', 'micr']):
        return True
    
    # Count indicators in broader context
    branch_count = sum(1 for indicator in branch_indicators if indicator in context_text)
    customer_count = sum(1 for indicator in customer_indicators if indicator in context_text)
    
    # If significantly more branch indicators, it's likely branch context
    return branch_count > customer_count + 1  # Bias towards customer unless clearly branch

# --- extractor -------------------------------------------------------------

class NameExtractor:
    NAME_ADDR_TITLE = re.compile(r"\bname\s*&?\s*address\b", re.I)
    # Same-line "Account Number … ) - Name" (allow various dashes)
    ACCOUNT_LINE_SAME = re.compile(
        r"account\s*(?:number|no)\b[^\n]*\)\s*[-—–:]\s*([A-Z][A-Z\s\.'-]{3,})",
        re.I,
    )
    
    # Pattern for labeled names like "Account Name :"
    LABELED_NAME_PATTERNS = [
        re.compile(r"account\s*name\s*:\s*([^\n\r]+)", re.I),
        re.compile(r"account\s*holder\s*name\s*:\s*([^\n\r]+)", re.I),
        re.compile(r"customer\s*name\s*:\s*([^\n\r]+)", re.I),
        re.compile(r"holder\s*name\s*:\s*([^\n\r]+)", re.I),
        # NEW: Context-aware name pattern
        re.compile(r"name\s*:-?\s*([^\n\r]+)", re.I),
    ]
    
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

    def _extract_from_tables(self, tables: List[Dict[str, Any]], window: int) -> Dict[str, Any]:
        """Extract names directly from table structure"""
        if not tables:
            return {"name": None, "confidence": 0.0, "evidence": None}
        
        for tbl_idx, tbl in enumerate(tables[:3]):
            rows = tbl.get("rows", [])
            
            for row_idx, row in enumerate(rows):
                for cell_idx, cell in enumerate(row):
                    if not cell:
                        continue
                        
                    cell_str = str(cell).strip()
                    
                    # Look for names that start with titles
                    if re.match(r"^(MR|MRS|MS|SHRI|SMT|DR)\s+[A-Z][A-Z\s]+$", cell_str, re.I):
                        # Check if this looks like a person's name
                        if _looks_like_name(cell_str):
                            # Additional check: make sure it's not in a branch context
                            # Check surrounding cells for branch indicators
                            context_cells = []
                            if cell_idx > 0 and row[cell_idx-1]:
                                context_cells.append(str(row[cell_idx-1]))
                            if cell_idx < len(row)-1 and row[cell_idx+1]:
                                context_cells.append(str(row[cell_idx+1]))
                            
                            context_text = " ".join(context_cells).lower()
                            if not any(indicator in context_text for indicator in ['branch', 'ifsc', 'micr']):
                                name = _title_if_caps(cell_str)
                                return {"name": name, "confidence": 0.85, "evidence": f"table cell with title ({window}p)"}
                    
                    # Also look for names without titles but in name-like positions
                    elif _looks_like_name(cell_str) and len(cell_str.split()) >= 2:
                        # Check if previous cells suggest this is a name context
                        prev_cells = []
                        for i in range(max(0, cell_idx-2), cell_idx):
                            if row[i]:
                                prev_cells.append(str(row[i]).lower())
                        
                        prev_text = " ".join(prev_cells)
                        # If previous context suggests customer info, this could be a name
                        if any(indicator in prev_text for indicator in ['account', 'customer', 'holder']):
                            name = _title_if_caps(cell_str)
                            return {"name": name, "confidence": 0.80, "evidence": f"table cell in customer context ({window}p)"}
        
        return {"name": None, "confidence": 0.0, "evidence": None}

    # ---- SAME logic, but scoped per window ----
    def _extract_from_window(self, raw_pages: List[Dict[str, Any]], tables: List[Dict[str, Any]] | None, window: int) -> Dict[str, Any]:
        # build text/lines from the first `window` pages
        pages_text = "\n".join(p.get("text") or "" for p in raw_pages[:window])
        lines = (pages_text or "").splitlines()

        # 0) NEW: Check for labeled names first (like "Account Name : Mr. ANURAG SINHA")
        for pattern in self.LABELED_NAME_PATTERNS:
            matches = pattern.finditer(pages_text)
            for match in matches:
                candidate = match.group(1).strip()
                
                # Check if this appears in branch context (right column)
                if _is_likely_branch_context(pages_text, match.start()):
                    if self.debug:
                        print(f"Skipping labeled name '{candidate}' - appears in branch context")
                    continue
                    
                if _looks_like_name(candidate):
                    # Keep titles like Mr., Mrs., etc.
                    nm = _title_if_caps(candidate)
                    return {"name": nm, "confidence": 0.95, "evidence": f"labeled name pattern (first {window}p)"}

        # 1) "Account Number ↵ … ) - NAME" (multi-line block)
        m_block = _NAME_AFTER_ACCOUNT_BLOCK.search(pages_text)
        if m_block:
            # Check if this appears in branch context
            if not _is_likely_branch_context(pages_text, m_block.start()):
                prefilled_name = _sanitize_name(m_block.group("who"))
                if prefilled_name:
                    return {"name": prefilled_name, "confidence": 0.92, "evidence": f"account-block pattern (first {window}p)"}

        # 2) Name & Address zone
        start, end = _find_zone(lines, self.NAME_ADDR_TITLE)
        if start != -1:
            for ln in lines[start:end][:6]:
                if _looks_like_name(ln):
                    nm = _title_if_caps(ln)  # Keep titles
                    return {"name": nm, "confidence": 0.95, "evidence": f"name&address zone (first {window}p)"}

        # 3) Account line – same line
        joined = "\n".join(lines)
        m = self.ACCOUNT_LINE_SAME.search(joined)
        if m:
            # Check if this appears in branch context
            if not _is_likely_branch_context(joined, m.start()):
                cand = m.group(1).strip()
                cand = re.split(r"\b(transaction|search|period|list)\b", cand, flags=re.I)[0].strip()
                tokens = [t for t in cand.split() if t.isalpha()]
                if 2 <= len(tokens) <= 5:
                    nm = _title_if_caps(" ".join(tokens))  # Keep titles
                    if _looks_like_name(nm):
                        return {"name": nm, "confidence": 0.88, "evidence": f"account line (same line, {window}p)"}

        # 4) Account line – next line after number
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
                    m2 = re.search(r"\)\s*[-—–:]\s*([A-Za-z][A-Za-z\s\.'/-]{3,})$", nxt)
                    if m2:
                        cand = m2.group(1)
                        cand = re.sub(r"\s*/\s*", " ", cand)
                        cand = " ".join(cand.split())
                        # DON'T strip titles
                        toks = cand.split()
                        if (2 <= len(toks) <= 5
                            and not any(ch.isdigit() for ch in cand)
                            and not HEADERISH.search(cand)
                            and not _CORPORATE.search(cand)):
                            return {"name": cand.title() if cand.isupper() else cand,
                                    "confidence": 0.90,
                                    "evidence": f"account line (next line, {window}p)"}
                    if _looks_like_name(nxt):
                        nm = _title_if_caps(nxt)  # Keep titles
                        return {"name": nm, "confidence": 0.86, "evidence": f"account line (next line fallback, {window}p)"}
                break

        # 5) Top-left block heuristic
        for ln in lines[:15]:
            if _looks_like_name(ln):
                nm = _title_if_caps(ln)  # Keep titles
                return {"name": nm, "confidence": 0.70, "evidence": f"top-left block ({window}p)"}

        # 6) NEW: Table-based extraction 
        if tables:
            table_result = self._extract_from_tables(tables, window)
            if table_result.get("name"):
                return table_result

        # 7) Table fallbacks
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
                                    nm = _title_if_caps(cand)  # Keep titles
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
                                nm = _title_if_caps(below.strip())  # Keep titles
                                return {"name": nm, "confidence": 0.62, "evidence": f"table below cell ({window}p)"}

        return {"name": None, "confidence": 0.0, "evidence": None}
    