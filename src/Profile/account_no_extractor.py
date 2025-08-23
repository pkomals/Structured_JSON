
# from __future__ import annotations
# from typing import List, Dict, Any, Optional, Tuple
# import re

# # ------------------------
# # Patterns & guard rails
# # ------------------------

# # common account labels
# ACCT_LABEL = re.compile(
#     r"\b(a(?:ccount)?\s*(?:no\.?|number|#)|a\/c\s*(?:no\.?|number)|account\s*id)\b",
#     re.I,
# )

# # labels that must NOT be interpreted as account number
# NOT_ACCOUNT_LABEL = re.compile(
#     r"\b(cust(?:omer)?\s*id|crn|cif|ucc|client\s*id|relationship\s*id|rm\s*contact|ifsc|micr|pin\s*code|pincode)\b",
#     re.I,
# )

# # (INR) tail often sits right after account_number in some UIs
# INR_TAIL = re.compile(r"\(INR\)", re.I)

# # acceptable account “shapes” (masked or plain)
# #  - plain digits    : 9–18 digits (avoid 6-digit pin / micr-esque)
# #  - masked patterns : 2+ digits, 3+ Xs, 2+ digits  OR  2+ Xs then 3+ digits  OR  3+ digits then 2+ Xs
# PLAIN_DIGITS = re.compile(r"\b\d{9,18}\b")
# MASKED_A = re.compile(r"\b\d{2,}[Xx\*]{3,}\d{2,}\b")
# MASKED_B = re.compile(r"\b[Xx\*]{2,}\d{3,}\b")
# MASKED_C = re.compile(r"\b\d{3,}[Xx\*]{2,}\b")

# # explicit exclusions (IFSC/MICR/PIN etc.)
# IFSC_RE = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b", re.I)
# MICR_RE = re.compile(r"\b\d{9}\b")
# PIN_RE  = re.compile(r"\b\d{6}\b")

# # “promo/marketing” pages often look like these
# PROMO_HINTS = re.compile(
#     r"(download\s+app|cashback|points|offer|emi|insurance|thank\s+you\s+for\s+banking|"
#     r"open\s+an\s+account|credit\s*card|debit\s*card|upi|scan\s+to\s+pay|advertisement)",
#     re.I,
# )

# def _is_promo_page(text: str) -> bool:
#     # lightweight heuristic: lots of promo words and very few numbers that look like dates/amounts
#     words = PROMO_HINTS.findall(text or "")
#     digits = re.findall(r"\d", text or "")
#     return len(words) >= 2 and len(digits) < 120  # tweakable

# def _clean(s: Optional[str]) -> Optional[str]:
#     if not s: return None
#     s = s.replace("cid:9", " ")
#     s = " ".join(s.split())
#     return s or None

# def _looks_like_account(candidate: str) -> bool:
#     if IFSC_RE.search(candidate) or MICR_RE.search(candidate) or PIN_RE.fullmatch(candidate):
#         return False
#     if PLAIN_DIGITS.fullmatch(candidate):
#         return True
#     if MASKED_A.fullmatch(candidate) or MASKED_B.fullmatch(candidate) or MASKED_C.fullmatch(candidate):
#         return True
#     return False

# def _score(candidate: str, context: str, labeled: bool) -> float:
#     score = 0.6
#     if labeled:
#         score += 0.3
#     if INR_TAIL.search(context):
#         score += 0.1
#     if NOT_ACCOUNT_LABEL.search(context):
#         score -= 0.6
#     # big penalty if it smells like IFSC/MICR/PIN
#     if IFSC_RE.search(candidate) or MICR_RE.search(candidate) or PIN_RE.fullmatch(candidate):
#         score -= 1.0
#     # small penalty if candidate is extremely short/long (but still passed _looks_like_account)
#     if len(candidate.replace(" ", "")) < 9 or len(candidate.replace(" ", "")) > 22:
#         score -= 0.1
#     return score

# class AccountNumberExtractor:
#     """
#     extract(raw_pages, tables=None, first_n_pages=2, skip_promos=True) -> {account_number, confidence, evidence}

#     Handles:
#       • first two *content* pages (skipping ad/promo-looking page 1 if needed)
#       • labeled text ("Account Number", "A/C No", etc.)
#       • table layouts (right cell / below cell)
#       • masked & unmasked patterns
#       • avoids Cust ID / CRN / IFSC / MICR / PIN
#     """

#     def extract(
#         self,
#         raw_pages: List[Dict[str, Any]],
#         tables: Optional[List[Dict[str, Any]]] = None,
#         first_n_pages: int = 2,
#         skip_promos: bool = True,
#     ) -> Dict[str, Any]:

#         # --------------------------
#         # pick pages to consider
#         # --------------------------
#         texts: List[str] = []
#         for p in raw_pages[:max(3, first_n_pages + 1)]:  # peek 3 to allow skipping ad-like page 1
#             t = p.get("text", "") or ""
#             if skip_promos and len(texts) == 0 and _is_promo_page(t):
#                 # skip first page if it looks like marketing
#                 continue
#             texts.append(t)
#             if len(texts) >= first_n_pages:
#                 break

#         full_text = "\n".join(texts)
#         lines = full_text.splitlines()

#         # --------------------------
#         # 1) labeled, inline in text
#         # --------------------------
#         best: Tuple[str, float, str] | None = None
#         for m in ACCT_LABEL.finditer(full_text):
#             # take same line (after the label)
#             line_start = full_text.rfind("\n", 0, m.start())
#             line_end   = full_text.find("\n", m.end())
#             if line_start == -1: line_start = 0
#             if line_end   == -1: line_end   = len(full_text)
#             line = full_text[line_start:line_end]

#             # candidates on same line after the label
#             tail = line[m.end() - line_start:]
#             cands = re.findall(r"([A-Za-z0-9Xx\*]{6,})", tail)
#             for c in cands[:3]:
#                 c = _clean(c) or ""
#                 if _looks_like_account(c) and not NOT_ACCOUNT_LABEL.search(line):
#                     sc = _score(c, line, labeled=True)
#                     item = (c, sc, "text labeled (same line)")
#                     if not best or sc > best[1]:
#                         best = item

#             # also check next line (common split label/value)
#             next_line_start = line_end + 1
#             next_line_end = full_text.find("\n", next_line_start)
#             if next_line_end == -1: next_line_end = len(full_text)
#             next_line = full_text[next_line_start:next_line_end]
#             cands = re.findall(r"([A-Za-z0-9Xx\*]{6,})", next_line)
#             for c in cands[:3]:
#                 c = _clean(c) or ""
#                 if _looks_like_account(c) and not NOT_ACCOUNT_LABEL.search(next_line):
#                     sc = _score(c, next_line, labeled=True)
#                     item = (c, sc, "text labeled (next line)")
#                     if not best or sc > best[1]:
#                         best = item

#         if best:
#             return {"account_number": best[0], "confidence": round(min(best[1], 0.99), 2), "evidence": best[2]}

#         # --------------------------
#         # 2) table forms
#         # --------------------------
#         if tables:
#             for tbl in tables[:3]:
#                 rows = tbl.get("rows", []) or []
#                 # right-cell
#                 for row in rows:
#                     for i, cell in enumerate(row):
#                         if not isinstance(cell, str): 
#                             continue
#                         cell_norm = _clean(cell) or ""
#                         if ACCT_LABEL.search(cell_norm) and not NOT_ACCOUNT_LABEL.search(cell_norm):
#                             if i + 1 < len(row) and isinstance(row[i + 1], str):
#                                 cand = _clean(row[i + 1]) or ""
#                                 if _looks_like_account(cand):
#                                     sc = _score(cand, cell_norm + " " + cand, labeled=True)
#                                     return {"account_number": cand, "confidence": round(min(sc, 0.99), 2), "evidence": "table right cell"}
#                 # below-cell (vertical layout)
#                 for ri in range(len(rows) - 1):
#                     row = rows[ri]
#                     nxt = rows[ri + 1]
#                     for ci, cell in enumerate(row):
#                         if not isinstance(cell, str): 
#                             continue
#                         cell_norm = _clean(cell) or ""
#                         if ACCT_LABEL.search(cell_norm) and not NOT_ACCOUNT_LABEL.search(cell_norm):
#                             below = nxt[ci] if ci < len(nxt) and isinstance(nxt[ci], str) else None
#                             if below:
#                                 cand = _clean(below) or ""
#                                 if _looks_like_account(cand):
#                                     sc = _score(cand, cell_norm + " " + cand, labeled=True)
#                                     return {"account_number": cand, "confidence": round(min(sc, 0.99), 2), "evidence": "table below cell"}

#         # --------------------------
#         # 3) unlabeled “account block” pattern:
#         #     04123…(INR) - NAME
#         # --------------------------
#         m = re.search(r"(^|\n)\s*([A-Za-z0-9Xx\*]{6,})\s*\(INR\)\s*[-–—:]\s*[A-Z].+$", full_text, re.I | re.M)
#         if m:
#             cand = _clean(m.group(2)) or ""
#             if _looks_like_account(cand):
#                 sc = _score(cand, m.group(0), labeled=False) + 0.1
#                 return {"account_number": cand, "confidence": round(min(sc, 0.99), 2), "evidence": "account line with (INR) - NAME"}

#         # --------------------------
#         # 4) last resort: any strong account-like token in top block
#         # --------------------------
#         for ln in lines[:40]:
#             for tok in re.findall(r"[A-Za-z0-9Xx\*]{6,}", ln or "")[:3]:
#                 tok = _clean(tok) or ""
#                 if _looks_like_account(tok) and not NOT_ACCOUNT_LABEL.search(ln):
#                     sc = _score(tok, ln, labeled=False)
#                     if sc >= 0.7:
#                         return {"account_number": tok, "confidence": round(min(sc, 0.95), 2), "evidence": "top block heuristic"}

#         return {"account_number": None, "confidence": 0.0, "evidence": None}
# src/fields/account_extractor.py
from __future__ import annotations
from typing import List, Dict, Any, Optional, Tuple
import re

# ---------- Patterns & guard rails ----------
ACCT_LABEL = re.compile(
    r"\b(a(?:ccount)?\s*(?:no\.?|number|#)|a\/c\s*(?:no\.?|number)|account\s*id)\b",
    re.I,
)

NOT_ACCOUNT_LABEL = re.compile(
    r"\b(cust(?:omer)?\s*id|crn|cif|ucc|client\s*id|relationship\s*id|rm\s*contact|"
    r"ifsc|micr|pin\s*code|pincode)\b",
    re.I,
)

INR_TAIL = re.compile(r"\(INR\)", re.I)

PLAIN_DIGITS = re.compile(r"\b\d{9,18}\b")      # 9–18 digits (avoid 6-digit PIN, 9-digit MICR handled below)
MASKED_A = re.compile(r"\b\d{2,}[Xx\*]{3,}\d{2,}\b")
MASKED_B = re.compile(r"\b[Xx\*]{2,}\d{3,}\b")
MASKED_C = re.compile(r"\b\d{3,}[Xx\*]{2,}\b")

IFSC_RE = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b", re.I)
MICR_RE = re.compile(r"\b\d{9}\b")
PIN_RE  = re.compile(r"\b\d{6}\b")

PROMO_HINTS = re.compile(
    r"(download\s+app|cashback|points|offer|emi|insurance|thank\s+you\s+for\s+banking|"
    r"open\s+an\s+account|credit\s*card|debit\s*card|upi|scan\s+to\s+pay|advertisement)",
    re.I,
)

def _is_promo_page(text: str) -> bool:
    words = PROMO_HINTS.findall(text or "")
    digits = re.findall(r"\d", text or "")
    return len(words) >= 2 and len(digits) < 120

def _clean(s: Optional[str]) -> Optional[str]:
    if not s: return None
    s = s.replace("cid:9", " ")
    s = " ".join(s.split())
    return s or None

def _looks_like_account(candidate: str) -> bool:
    if IFSC_RE.search(candidate) or MICR_RE.fullmatch(candidate) or PIN_RE.fullmatch(candidate):
        return False
    if PLAIN_DIGITS.fullmatch(candidate):
        return True
    if MASKED_A.fullmatch(candidate) or MASKED_B.fullmatch(candidate) or MASKED_C.fullmatch(candidate):
        return True
    return False

def _score(candidate: str, context: str, labeled: bool) -> float:
    score = 0.6
    if labeled: score += 0.3
    if INR_TAIL.search(context): score += 0.1
    if NOT_ACCOUNT_LABEL.search(context): score -= 0.6
    if IFSC_RE.search(candidate) or MICR_RE.fullmatch(candidate) or PIN_RE.fullmatch(candidate):
        score -= 1.0
    if len(candidate.replace(" ", "")) < 9 or len(candidate.replace(" ", "")) > 22:
        score -= 0.1
    return score

def _dedupe_keep_best(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best_by_key: Dict[str, Dict[str, Any]] = {}
    for it in items:
        key = it["account_number"].replace(" ", "")
        prev = best_by_key.get(key)
        if prev is None or it["confidence"] > prev["confidence"]:
            best_by_key[key] = it
    # stable sort by confidence desc
    return sorted(best_by_key.values(), key=lambda x: (-x["confidence"], x["account_number"]))

class AccountNumberExtractor:
    """
    extract(..., return_all=False) -> single best account
    extract(..., return_all=True)  -> list of all accounts found (unique, scored)
    """

    def extract(
        self,
        raw_pages: List[Dict[str, Any]],
        tables: Optional[List[Dict[str, Any]]] = None,
        *,
        first_n_pages: int = 2,
        skip_promos: bool = True,
        return_all: bool = False,
    ) -> Dict[str, Any] | List[Dict[str, Any]]:

        # ---- choose content pages (skip ad-like page 1 if needed) ----
        texts: List[str] = []
        for p in raw_pages[:max(3, first_n_pages + 1)]:
            t = p.get("text", "") or ""
            if skip_promos and len(texts) == 0 and _is_promo_page(t):
                continue
            texts.append(t)
            if len(texts) >= first_n_pages:
                break

        full_text = "\n".join(texts)
        lines = full_text.splitlines()

        candidates: List[Dict[str, Any]] = []

        # ---- 1) labeled occurrences in text (same line & next line) ----
        for m in ACCT_LABEL.finditer(full_text):
            line_start = full_text.rfind("\n", 0, m.start())
            line_end   = full_text.find("\n", m.end())
            if line_start == -1: line_start = 0
            if line_end   == -1: line_end   = len(full_text)
            line = full_text[line_start:line_end]

            # same line
            tail = line[m.end() - line_start:]
            for c in re.findall(r"([A-Za-z0-9Xx\*]{6,})", tail)[:5]:
                c = _clean(c) or ""
                if _looks_like_account(c) and not NOT_ACCOUNT_LABEL.search(line):
                    sc = _score(c, line, labeled=True)
                    candidates.append({"account_number": c, "confidence": round(min(sc, 0.99), 2), "evidence": "text labeled (same line)"})

            # next line
            next_line_start = line_end + 1
            next_line_end = full_text.find("\n", next_line_start)
            if next_line_end == -1: next_line_end = len(full_text)
            next_line = full_text[next_line_start:next_line_end]
            for c in re.findall(r"([A-Za-z0-9Xx\*]{6,})", next_line)[:5]:
                c = _clean(c) or ""
                if _looks_like_account(c) and not NOT_ACCOUNT_LABEL.search(next_line):
                    sc = _score(c, next_line, labeled=True)
                    candidates.append({"account_number": c, "confidence": round(min(sc, 0.99), 2), "evidence": "text labeled (next line)"})

        # ---- 2) tables (right cell & below cell) ----
        if tables:
            for tbl in tables[:5]:
                rows = tbl.get("rows", []) or []
                # right cell
                for row in rows:
                    for i, cell in enumerate(row):
                        if not isinstance(cell, str): continue
                        cell_norm = _clean(cell) or ""
                        if ACCT_LABEL.search(cell_norm) and not NOT_ACCOUNT_LABEL.search(cell_norm):
                            if i + 1 < len(row) and isinstance(row[i + 1], str):
                                cand = _clean(row[i + 1]) or ""
                                if _looks_like_account(cand):
                                    sc = _score(cand, cell_norm + " " + cand, labeled=True)
                                    candidates.append({"account_number": cand, "confidence": round(min(sc, 0.99), 2), "evidence": "table right cell"})
                # below cell
                for ri in range(len(rows) - 1):
                    row = rows[ri]
                    nxt = rows[ri + 1]
                    for ci, cell in enumerate(row):
                        if not isinstance(cell, str): continue
                        cell_norm = _clean(cell) or ""
                        if ACCT_LABEL.search(cell_norm) and not NOT_ACCOUNT_LABEL.search(cell_norm):
                            below = nxt[ci] if ci < len(nxt) and isinstance(nxt[ci], str) else None
                            if below:
                                cand = _clean(below) or ""
                                if _looks_like_account(cand):
                                    sc = _score(cand, cell_norm + " " + cand, labeled=True)
                                    candidates.append({"account_number": cand, "confidence": round(min(sc, 0.99), 2), "evidence": "table below cell"})

        # ---- 3) unlabeled “N…(INR) - NAME” line ----
        m = re.search(r"(^|\n)\s*([A-Za-z0-9Xx\*]{6,})\s*\(INR\)\s*[-–—:]\s*[A-Z].+$", full_text, re.I | re.M)
        if m:
            cand = _clean(m.group(2)) or ""
            if _looks_like_account(cand):
                sc = _score(cand, m.group(0), labeled=False) + 0.1
                candidates.append({"account_number": cand, "confidence": round(min(sc, 0.99), 2), "evidence": "account line with (INR) - NAME"})

        # ---- 4) top-block heuristic (useful when a table lists many accounts with no labels) ----
        for ln in lines[:80]:
            if NOT_ACCOUNT_LABEL.search(ln):  # skip rows that say “Customer ID”, etc.
                continue
            for tok in re.findall(r"[A-Za-z0-9Xx\*]{6,}", ln or "")[:6]:
                tok = _clean(tok) or ""
                if _looks_like_account(tok):
                    sc = _score(tok, ln, labeled=False)
                    if sc >= 0.72:  # slightly higher bar to avoid noise
                        candidates.append({"account_number": tok, "confidence": round(min(sc, 0.95), 2), "evidence": "top block heuristic"})

        results = _dedupe_keep_best(candidates)

        if return_all:
            return results
        # single best for backward-compat
        if not results:
            return {"account_number": None, "confidence": 0.0, "evidence": None}
        best = results[0]
        return {"account_number": best["account_number"], "confidence": best["confidence"], "evidence": best["evidence"]}
