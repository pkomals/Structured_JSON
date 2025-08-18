import re
from datetime import datetime
from typing import List, Dict, Any, Optional

DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %b %Y", "%d %b '%y", "%d/%m/%y")
CITIES_HINT = r"(?:mumbai|delhi|bengaluru|bangalore|chennai|kolkata|pune|hyderabad|gurgaon|noida|ahmedabad)"
PIN_RE = r"\b\d{6}\b"  # IN pincode

def _to_epoch_ms(s: str) -> Optional[int]:
    if not s:
        return None
    s = s.strip().replace("’", "'")
    for fmt in DATE_FORMATS:
        try:
            return int(datetime.strptime(s, fmt).timestamp() * 1000)
        except Exception:
            pass
    return None

def _clean(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v = v.strip()
    return v if v else None

def _is_headerish(s: str) -> bool:
    return bool(re.search(r"(statement|account|summary|period|balance|branch|ifsc|micr|page\s+\d+)", s, re.I))

def _looks_like_name(s: str) -> bool:
    """
    Heuristic: allow ALL-CAPS or Title Case names (2–5 tokens), disallow obvious headers.
    """
    s = s.strip()
    if not s or ":" in s or len(s) > 64:
        return False
    if _is_headerish(s):
        return False
    # avoid bank/corporate words
    if re.search(r"(bank|limited|ltd|pvt|plc|finance|private|public)", s, re.I):
        return False
    # tokens: allow letters, dots, hyphens, apostrophes
    token_ok = re.fullmatch(r"[A-Za-z][A-Za-z\.\-']*(?:\s+[A-Za-z][A-Za-z\.\-']*){1,4}", s)
    if token_ok:
        return True
    # fallback: ALL-CAPS with 2–4 words (e.g., ANURAG SINHA)
    if s.isupper() and 2 <= len(s.split()) <= 4 and re.fullmatch(r"[A-Z][A-Z\.\-']*(?:\s+[A-Z][A-Z\.\-']*){1,3}", s):
        return True
    return False

def _looks_like_address(s: str) -> bool:
    s = s.strip()
    if not s or len(s) < 5:
        return False
    if _is_headerish(s):
        return False
    if re.search(r"\d", s):
        return True  # house no, pin, etc.
    if "," in s:
        return True
    if re.search(r"(road|rd\.|street|st\.|lane|ln\.|nagar|vihar|sector|block|phase|layout|society|apartment|apt\.|tower|villa|project)", s, re.I):
        return True
    if re.search(CITIES_HINT, s, re.I):
        return True
    if re.search(PIN_RE, s):
        return True
    return False


class ProfileExtractor:
    # Label variants (expanded)
    NAME_LABELS = r"(?:Account\s*Holder(?:\s*Name)?|Customer\s*Name|Holder\s*Name)"
    ACCT_TYPE_LABELS = r"(?:Account\s*Type|A/c\s*Type|A\.?C\.?\s*Type)"
    ACCT_NO_LABELS = r"(?:Account\s*Number|A/c\s*No\.?|A/C\s*No\.?)"
    CUST_ID_LABELS = r"(?:Customer\s*ID|Cust(?:omer)?\s*ID|Customer\s*No\.?|Cust\s*No\.?)"
    NOMINEE_LABELS = r"(?:Nominee|Nominee\s*Name|Nomination\s*Status|Nomination\s*Registered)"
    MOBILE_LABELS = r"(?:Registered\s*Mobile\s*(?:No\.?|Number)?|Mobile|Phone|Contact\s*No\.?)"
    EMAIL_LABELS = r"(?:Registered\s*Email\s*(?:ID|Address)|Email|E-mail)"
    ADDRESS_LABELS = r"(?:Address|Mailing\s*Address|Communication\s*Address)"

    PAN_RE = r"\b([A-Z]{5}\d{4}[A-Z])\b"
    MASKED_AC_RE = r"([Xx\*]{4,}\s*\d{3,})"

    def __init__(self, debug: bool = False, preview_lines: int = 24):
        self.debug = debug
        self.preview_lines = preview_lines

    def _infer_name_address_from_block(self, lines: List[str]) -> Dict[str, Optional[str]]:
        head = [ln.strip() for ln in lines[: self.preview_lines] if ln and ln.strip()]
        name = None
        addr_lines: List[str] = []
        picked_name_idx = None
        picked_addr_indices: List[int] = []

        for i, line in enumerate(head):
            # skip obvious noise
            if _is_headerish(line) or re.search(r"Cust(omer)?\s*ID|KYC|CKYC|IFSC|MICR|PAN|Mobile|Email", line, re.I):
                continue
            if name is None and _looks_like_name(line):
                name = line
                picked_name_idx = i
                # accumulate address lines right after name
                j = i + 1
                while j < len(head) and len(addr_lines) < 5:
                    nxt = head[j]
                    if _is_headerish(nxt) or re.search(r":\s*$", nxt) or re.search(r"Cust(omer)?\s*ID|KYC|CKYC|IFSC|MICR|PAN|Mobile|Email", nxt, re.I):
                        break
                    if _looks_like_address(nxt):
                        addr_lines.append(nxt)
                        picked_addr_indices.append(j)
                        j += 1
                        continue
                    # stop at first non-addressy line
                    break
                break

        if self.debug:
            print("\n— Debug: Unlabeled block scan (first lines) —")
            for idx, ln in enumerate(head):
                tag = ""
                if idx == (picked_name_idx if picked_name_idx is not None else -1):
                    tag = "  <-- name"
                elif idx in picked_addr_indices:
                    tag = "  <-- address"
                print(f"{idx:02d}: {ln}{tag}")

        return {"name": _clean(name), "address": _clean(", ".join(addr_lines)) if addr_lines else None}

    def extract(self, raw_pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        pages_text = "\n".join(p.get("text") or "" for p in raw_pages[:2])
        lines = (pages_text or "").splitlines()

        out = {
            "dob": None, "pan": None, "name": None, "type": None,
            "email": None, "fipId": None, "mobile": None, "address": None,
            "nominee": None, "landLine": None, "account_type": None,
            "linkedAccRef": None, "fnrkAccountId": None,
            "ckycCompliance": None, "maskedAccNumber": None,
        }

        # ---- Label-based extraction (expanded) ----

        # PAN: full or masked
        m = re.search(self.PAN_RE, pages_text)
        if m:
            out["pan"] = m.group(1)
        else:
            m = re.search(r"\bPAN\s*[:\-]\s*([A-Z0-9X]+)", pages_text, re.I)
            if m:
                out["pan"] = _clean(m.group(1))  # masked PAN accepted

        # Name (labeled)
        m = re.search(self.NAME_LABELS + r"\s*[:\-]\s*([^\n]+)", pages_text, re.I)
        if m:
            out["name"] = _clean(m.group(1))

        # Account type (Savings/Current)
        m = re.search(self.ACCT_TYPE_LABELS + r"\s*[:\-]\s*([A-Za-z ]+)", pages_text, re.I)
        if m:
            out["account_type"] = _clean(m.group(1))
        else:
            # Sometimes appears as "Savings     Account(s)"
            m = re.search(r"\b(Savings|Current)\s+Account\(s\)", pages_text, re.I)
            if m:
                out["account_type"] = _clean(m.group(1).title())

        # Account No (masked) or any masked A/C pattern
        m = re.search(self.ACCT_NO_LABELS + r"\s*[:\-]\s*([^\n]+)", pages_text, re.I)
        if m:
            cand = m.group(1)
            m2 = re.search(self.MASKED_AC_RE, cand)
            out["maskedAccNumber"] = _clean(m2.group(1)) if m2 else _clean(cand)
        else:
            m2 = re.search(self.MASKED_AC_RE, pages_text)
            if m2:
                out["maskedAccNumber"] = _clean(m2.group(1))

        # Cust ID as potential masked account fallback
        cust_mask = None
        m = re.search(self.CUST_ID_LABELS + r"\s*[:\-]\s*([^\n]+)", pages_text, re.I)
        if m:
            cust_mask = _clean(m.group(1))
        if not out["maskedAccNumber"] and cust_mask:
            out["maskedAccNumber"] = cust_mask  # comment this if you don't want this fallback

        # Email (registered email may be masked without '@')
        m = re.search(self.EMAIL_LABELS + r"\s*[:\-]\s*([^\n]+)", pages_text, re.I)
        if m:
            out["email"] = _clean(m.group(1))
        else:
            # any email-looking token
            m = re.search(r"([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})", pages_text)
            if m:
                out["email"] = _clean(m.group(1))

        # Mobile (masked accepted)
        m = re.search(self.MOBILE_LABELS + r"\s*[:\-]\s*([+\dXx][\dXx\s\-]{5,})", pages_text, re.I)
        if m:
            out["mobile"] = _clean(m.group(1)).replace(" ", "")

        # Nominee (e.g., "Nomination Registered")
        m = re.search(self.NOMINEE_LABELS + r"(?:\s*[:\-]\s*([^\n]+))?", pages_text, re.I)
        if m:
            # If no explicit value, but label mentions Registered, normalize to "REGISTERED"
            val = m.group(1)
            out["nominee"] = _clean(val) if val else "REGISTERED"

        # Labeled multi-line address
        m = re.search(self.ADDRESS_LABELS + r"\s*[:\-]\s*([^\n]+)", pages_text, re.I)
        if m:
            start = m.start(1)
            tail = pages_text[start:].splitlines()
            buf = []
            for line in tail:
                if _is_headerish(line) or re.search(r":\s*$", line):
                    break
                if re.search(self.NAME_LABELS + "|" + self.ACCT_NO_LABELS + "|" + self.EMAIL_LABELS, line, re.I):
                    break
                if not line.strip():
                    break
                buf.append(line.strip())
                if len(buf) > 5:
                    break
            out["address"] = _clean(", ".join([l for l in buf if l]))

        # DOB
        m = re.search(r"(?:Date\s*of\s*Birth|DOB)\s*[:\-]\s*([0-9]{1,2}[\/\-][0-9]{1,2}[\/\-][0-9]{2,4})", pages_text, re.I)
        if m:
            out["dob"] = _to_epoch_ms(m.group(1))

        # CKYC (optional signals)
        if re.search(r"\bCKYC\b.+Compliant", pages_text, re.I):
            out["ckycCompliance"] = True
        elif re.search(r"\bCKYC\b.+Non[- ]?Compliant", pages_text, re.I):
            out["ckycCompliance"] = False
        # treat "KYC Status: Updated" as neutral → leave None

        # ---- Unlabeled fallback for name + address ----
        if not out["name"] or not out["address"]:
            inferred = self._infer_name_address_from_block(lines)
            if self.debug:
                print("\n— Debug: Fallback picked —")
                print("name   :", inferred.get("name"))
                print("address:", inferred.get("address"))
            out["name"] = out["name"] or inferred.get("name")
            out["address"] = out["address"] or inferred.get("address")

        if self.debug:
            print("\n— ProfileExtractor output —")
            for k, v in out.items():
                print(f"{k:18s}: {v}")

        # Return a profile only if something was actually found
        return [out] if any(v not in (None, "") for v in out.values()) else []
