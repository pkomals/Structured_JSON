# src/fields/email_extractor.py
from __future__ import annotations
from typing import List, Dict, Any, Optional, Tuple
import re

# --- label variants (case-insensitive) ---
EMAIL_LABELS = re.compile(
    r"\b(customer\s*)?(e[-\s]?mail|email)\s*(id|address)?\b", re.I
)

# things that usually indicate staff/branch mailboxes (to exclude)
NON_CUSTOMER_CONTEXT = re.compile(
    r"\b(RM|Rel(?:ationship)?\s*Manager|Branch|Bank|Corporate|Care|Support|Helpdesk|Service\s*Desk)\b",
    re.I,
)

# banky domains / shared mailboxes (add yours here)
BANKY_DOMAINS = re.compile(
    r"@(hdfcbank|icicibank|axisbank|sbi|yesbank|kotak|rblbank|aubank|idfcfirst|indusind|federalbank|bandhanbank|iob|pnb|boi|bankofbaroda)\.(com|co\.in|in)$",
    re.I,
)

# normal email + masked variants (uppercase allowed)
EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)

# some banks print masked emails without '@' or with Xs, try to catch a few forms
MASKY_RE = re.compile(
    r"\b[A-Z0-9._%+\-]*X{2,}[A-Z0-9._%+\-]*@?[A-Z0-9.\-]+\.(com|in|co\.in)\b",
    re.I
)

# helpers -----------------------------------------------------------------

def _norm(s: str) -> str:
    s = s.strip().rstrip(" ,;:|")
    # many PDFs shout in caps
    return s

def _tokenize_name(name_hint: Optional[str]) -> list[str]:
    if not name_hint:
        return []
    return [t.lower() for t in re.findall(r"[A-Za-z]+", name_hint)]

def _looks_like_masked(s: str) -> bool:
    return bool(re.search(r"X{2,}", s, re.I))

def _context_is_staff(lines: List[str], idx: int, radius: int = 2) -> bool:
    lo = max(0, idx - radius)
    hi = min(len(lines), idx + radius + 1)
    ctx = " ".join(lines[lo:hi])
    return bool(NON_CUSTOMER_CONTEXT.search(ctx) or BANKY_DOMAINS.search(ctx))

def _score_candidate(addr: str, name_tokens: list[str]) -> float:
    score = 1.0
    local = addr.split("@")[0].lower()
    dom = addr.split("@")[1].lower() if "@" in addr else ""

    # penalize banky domains
    if BANKY_DOMAINS.search("@" + dom):
        score -= 0.8

    # boost if name is present in local part (either part of full name)
    if name_tokens and any(t in local for t in name_tokens if len(t) >= 3):
        score += 0.6

    # penalize noreply/service/mailers
    if re.search(r"\b(no[-_\.]?reply|service|support|help|donotreply)\b", local):
        score -= 0.5

    # penalize weird locals (pure digits)
    if re.fullmatch(r"\d{6,}", local):
        score -= 0.7

    # slight boost if not masked
    if not _looks_like_masked(addr):
        score += 0.15

    return score

# main extractor -----------------------------------------------------------

class EmailExtractor:
    """
    extract(raw_pages, tables=None, name_hint=None, first_n_pages=2) -> {email, confidence, evidence}
    Strategy:
      1) Handle label/value split across lines.
      2) Harvest every email-like token from text (and table cells).
      3) Score by (a) not bank/staff, (b) matches user's name, (c) not masked, (d) context.
      4) Return best passing a threshold.
    """
    def extract(
        self,
        raw_pages: List[Dict[str, Any]],
        tables: Optional[List[Dict[str, Any]]] = None,
        name_hint: Optional[str] = None,
        first_n_pages: int = 2,
    ) -> Dict[str, Any]:

        pages_text = "\n".join(p.get("text", "") or "" for p in raw_pages[:first_n_pages])
        lines = pages_text.splitlines()
        name_tokens = _tokenize_name(name_hint)

        # 0) label/value across lines
        #   A) label on one line, colon next, value next
        m = re.search(
            r"(?:^|\n)\s*customer\s*email(?:\s*id|\s*address)?\s*$"
            r"(?:\r?\n)\s*:\s*([^\s].+)$",
            pages_text, re.I | re.M,
        )
        if m:
            cand = _norm(m.group(1))
            # pull first email-looking token within that line
            m2 = EMAIL_RE.search(cand) or MASKY_RE.search(cand)
            if m2:
                addr = _norm(m2.group(0))
                if not BANKY_DOMAINS.search(addr):
                    return {"email": addr, "confidence": 0.95, "evidence": "label above, value below"}

        #   B) label with colon, value on next line
        m = re.search(
            r"(?:^|\n)\s*customer\s*email(?:\s*id|\s*address)?\s*:\s*$"
            r"(?:\r?\n)\s*([^\s].+)$",
            pages_text, re.I | re.M,
        )
        if m:
            cand = _norm(m.group(1))
            m2 = EMAIL_RE.search(cand) or MASKY_RE.search(cand)
            if m2:
                addr = _norm(m2.group(0))
                if not BANKY_DOMAINS.search(addr):
                    return {"email": addr, "confidence": 0.95, "evidence": "label+colon, value next line"}

        #   C) label, then look within next 2 lines
        for i, ln in enumerate(lines):
            if EMAIL_LABELS.search(ln):
                for k in (1, 2):
                    if i + k < len(lines):
                        cand_line = lines[i + k]
                        m2 = EMAIL_RE.search(cand_line) or MASKY_RE.search(cand_line)
                        if m2:
                            addr = _norm(m2.group(0))
                            if not _context_is_staff(lines, i):
                                return {"email": addr, "confidence": 0.92, "evidence": "label within 2 lines"}

        # 1) from tables (right/under cell)
        candidates: list[Tuple[str, float, str, int]] = []  # (addr, score, evidence, line_idx_for_ctx)
        if tables:
            for tbl in tables[:3]:
                rows = tbl.get("rows", []) or []
                for ri in range(len(rows)):
                    row = rows[ri]
                    for ci, cell in enumerate(row):
                        if not isinstance(cell, str):
                            continue
                        if EMAIL_LABELS.search(cell) and not NON_CUSTOMER_CONTEXT.search(cell):
                            # right cell
                            if ci + 1 < len(row) and isinstance(row[ci + 1], str):
                                for m in (EMAIL_RE.findall(row[ci + 1]) or MASKY_RE.findall(row[ci + 1])):
                                    addr = _norm(m if isinstance(m, str) else m[0])
                                    score = _score_candidate(addr, name_tokens)
                                    candidates.append((addr, score, "table right cell", -1))
                            # below cell
                            if ri + 1 < len(rows) and ci < len(rows[ri + 1]) and isinstance(rows[ri + 1][ci], str):
                                for m in (EMAIL_RE.findall(rows[ri + 1][ci]) or MASKY_RE.findall(rows[ri + 1][ci])):
                                    addr = _norm(m if isinstance(m, str) else m[0])
                                    score = _score_candidate(addr, name_tokens)
                                    candidates.append((addr, score, "table below cell", -1))

        # 2) harvest all emails from text
        all_text_emails = [*_unique(EMAIL_RE.findall(pages_text))]
        # include masked-ish as a last resort
        all_text_emails += [*_unique(MASKY_RE.findall(pages_text))]  # returns tuples for group, normalize below
        # normalize any tuple capture
        normed = []
        for e in all_text_emails:
            if isinstance(e, tuple):
                # MASKY_RE captured TLD; re-find full span for safety
                m = MASKY_RE.search(pages_text)
                if m:
                    normed.append(_norm(m.group(0)))
            else:
                normed.append(_norm(e))
        # score them with context
        for idx, ln in enumerate(lines):
            for m in EMAIL_RE.finditer(ln):
                addr = _norm(m.group(0))
                if _context_is_staff(lines, idx):
                    continue
                score = _score_candidate(addr, name_tokens)
                candidates.append((addr, score, "text", idx))
            for m in MASKY_RE.finditer(ln):
                addr = _norm(m.group(0))
                if _context_is_staff(lines, idx):
                    continue
                score = _score_candidate(addr, name_tokens) - 0.05  # small penalty for masked
                candidates.append((addr, score, "text(masked)", idx))

        # keep best non‑bank, non‑staff candidate
        if candidates:
            candidates.sort(key=lambda t: t[1], reverse=True)
            best = candidates[0]
            if best[1] >= 0.6:  # threshold
                return {"email": best[0], "confidence": round(min(0.99, 0.6 + best[1] / 2), 2), "evidence": best[2]}

        return {"email": None, "confidence": 0.0, "evidence": None}


# helpers -----------------------------------------------------------------

def _unique(xs):
    seen = set()
    for x in xs:
        if x not in seen:
            seen.add(x)
            yield x
