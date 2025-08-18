import re
from datetime import datetime
from typing import List, Dict, Any, Optional

DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %b %Y", "%d %b '%y", "%d/%m/%y")
CITIES_HINT = r"(?:mumbai|delhi|bengaluru|bangalore|chennai|kolkata|pune|hyderabad|gurgaon|noida|ahmedabad)"
PIN_RE = r"\b\d{6}\b"  # IN pincode
ADDRESS_STOPWORDS = ["pan", "email", "mobile", "landline", "nominee", "ckyc", "account"]

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
    if re.search(r"(road|rd\.|street|st\.|lane|ln\.|nagar|complex|chs|vihar|sector|block|phase|layout|society|apartment|apt\.|tower|villa|project)", s, re.I):
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
        self.tables = [] 

    
    # Update fallback
    def _extract_fallback(self, lines: list[str]) -> dict:
        result = {
            "name": None,
            "address": None
        }

        for i, line in enumerate(lines):
            line = line.strip()
            if line:
                # Assume the first valid non-empty line is the name
                result["name"] = line.title()
                addr_lines = []

                # Collect following lines for address
                for j in range(i + 1, min(i + 7, len(lines))):
                    next_line = lines[j].strip()
                    lower = next_line.lower()
                    if ":" in next_line or any(stop in lower for stop in ADDRESS_STOPWORDS):
                        break
                    addr_lines.append(next_line)

                if addr_lines:
                    result["address"] = ", ".join(addr_lines)
                break

        return result


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

        # Account No (prefer visible or masked account number)
        # m = re.search(self.ACCT_NO_LABELS + r"\s*[:\-]\s*([^\n]+)", pages_text, re.I)
        # acct_number = None
        # if m:
        #     cand = m.group(1).strip()
        #     # Accept either masked format or numeric (≥6 digits)
        #     if re.match(r"[Xx\*]{2,}[\dXx]{3,}", cand):
        #         acct_number = cand
        #     elif re.match(r"\d{6,}", cand):  # unmasked
        #         acct_number = cand

        # # Fallback: look for any masked pattern in full text
        # if not acct_number:
        #     m2 = re.search(self.MASKED_AC_RE, pages_text)
        #     if m2:
        #         acct_number = m2.group(1).strip()

        # # # Fallback: Cust ID only if nothing else
        # # if not acct_number:
        # #     m = re.search(self.CUST_ID_LABELS + r"\s*[:\-]\s*([^\n]+)", pages_text, re.I)
        # #     if m:
        # #         acct_number = _clean(m.group(1))

        # out["maskedAccNumber"] = acct_number
        acct_number = None

        m = re.search(self.ACCT_NO_LABELS + r"\s*[:\-]\s*([^\n]+)", pages_text, re.I)
        if m:
            cand = m.group(1).strip()
            if re.match(r"[Xx\*]{2,}[\dXx]{3,}", cand) or re.match(r"\d{6,}", cand):
                acct_number = cand

        # 2. Try tables (if available)
        if not acct_number and self.tables:
            acct_number = self._extract_account_number_from_tables(self.tables)

        # 3. Try any masked pattern in text
        if not acct_number:
            m2 = re.search(self.MASKED_AC_RE, pages_text)
            if m2:
                acct_number = m2.group(1).strip()

        # # 4. Fallback: Cust ID (only if nothing else found)
        # if not acct_number:
        #     m = re.search(self.CUST_ID_LABELS + r"\s*[:\-]\s*([^\n]+)", pages_text, re.I)
        #     if m:
        #         cust_id = _clean(m.group(1))
        #         acct_number = cust_id

        out["maskedAccNumber"] = acct_number
            


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
        
        
        # ---- Unlabeled fallback (name and/or address) ----
        needs_name = not out["name"]
        needs_address = not out["address"]

        if needs_name or needs_address:
            inferred = self._infer_name_address_from_block(lines)

            if self.debug:
                print("\n— Debug: Fallback picked —")
                if needs_name:
                    print("name   :", inferred.get("name"))
                if needs_address:
                    print("address:", inferred.get("address"))

            if needs_name:
                out["name"] = inferred.get("name")
            if needs_address:
                out["address"] = inferred.get("address")

        # Final preview
        if self.debug:
            print("\n— ProfileExtractor output —")
            for k, v in out.items():
                print(f"{k:<18}: {v}")

        return [out]
    
    def _extract_account_number_from_tables(self, tables: List[Dict[str, Any]]) -> Optional[str]:
        """
        Enhanced logic to extract account number from:
        - right-side neighbor cell (horizontal)
        - same cell (colon-separated)
        - below cell (vertical)
        - single-column label-value tables (special case)
        """
        for table in tables[:2]:  # only check first 2 tables
            rows = table.get("rows", [])
            for i, row in enumerate(rows):
                for j, cell in enumerate(row):
                    if not isinstance(cell, str):
                        continue

                    # Case 1: single-cell match like 'Account No: XXXXX'
                    if re.search(r"(Account\s*Number|A/c\s*No\.?|A/C\s*No\.?)", cell, re.I):
                        match = re.search(r":\s*([\wXx\*]+)", cell)
                        if match:
                            return match.group(1)

                        # Case 2: vertical format → next row, same column
                        if i + 1 < len(rows):
                            below_cell = rows[i + 1][j]
                            if isinstance(below_cell, str):
                                candidate = below_cell.strip()
                                if re.match(r"[Xx\*]{2,}[\dXx]{3,}", candidate) or re.match(r"\d{6,}", candidate):
                                    return candidate

            # Special case: single-column label-value table
            if len(rows) >= 2 and len(rows[0]) == 1 and len(rows[1]) == 1:
                label = rows[0][0]
                value = rows[1][0]
                if (
                    isinstance(label, str)
                    and re.search(r"(Account\s*Number|A/c\s*No\.?|A/C\s*No\.?)", label, re.I)
                    and isinstance(value, str)
                ):
                    value = value.strip()
                    if re.match(r"[Xx\*]{2,}[\dXx]{3,}", value) or re.match(r"\d{6,}", value):
                        return value

        return None



    def _flatten_lines(self, pages: List[dict]) -> List[str]:
        lines = []
        for page in pages[:2]:
            page_lines = page.get("text", "").splitlines()
            lines.extend(page_lines)
        return lines

    # def _infer_name_address_from_block(self, lines: List[str]) -> dict:
    #     name = None
    #     address_lines = []

    #     for i, line in enumerate(lines[:15]):
    #         line_clean = line.strip()

    #         # Skip metadata/header/footer junk
    #         if not line_clean or re.search(r"^page \d+", line_clean.lower()) or "statement" in line_clean.lower():
    #             continue

    #         # Heuristic: Line 1 = name (usually ALL CAPS or Title Case, short line)
    #         if not name and (
    #             line_clean.isupper()
    #             or re.match(r"^[A-Z][a-z]+(?: [A-Z][a-z]+)*$", line_clean)
    #         ):
    #             name = line_clean
    #             continue

    #         # Heuristic: Line contains address-like terms
    #         if name and len(line_clean.split()) >= 2 and any(x in line_clean.lower() for x in ["road", "villa", "nagar", "lane", "block", "floor", "bengaluru", "karnataka", "pin", "india"]):
    #             address_lines.append(line_clean)

    #         # Break if we collected enough
    #         if len(address_lines) >= 4:
    #             break

    #     address = " ".join(address_lines).strip() if address_lines else None

    #     return {
    #         "name": name,
    #         "address": address
    #     }
    def _infer_name_address_from_block(self, lines: List[str]) -> dict:
        name = None
        address_lines = []

        for i, line in enumerate(lines[:15]):
            line_clean = line.strip()

            # Skip metadata/header/footer junk
            if not line_clean or re.search(r"^page \d+", line_clean.lower()) or "statement" in line_clean.lower():
                continue

            # Heuristic: Name line (usually short, all caps or title case, no digits)
            if not name and (
                line_clean.isupper()
                or re.match(r"^[A-Z][a-z]+(?: [A-Z][a-z]+)*$", line_clean)
            ) and not any(char.isdigit() for char in line_clean):
                name = line_clean
                continue

            # After name, anything with 2+ words that doesn't look like metadata is candidate for address
            if name and len(line_clean.split()) >= 2:
                if any(word in line_clean.lower() for word in [
                    "road", "lane", "street", "villa", "nagar","chs","complex", "block", "floor", "apartment", "karnataka", "pin", "bengaluru", "india"
                ]) or not any(keyword in line_clean.lower() for keyword in ["cust id", "email", "mobile", "pan", "nominee"]):
                    address_lines.append(line_clean)

            # Stop collecting if address spans too long
            if len(address_lines) >= 5:
                break

        # If only one good address-like line exists (common in some banks), still use it
        address = " ".join(address_lines).strip() if address_lines else None

        return {
            "name": name,
            "address": address
        }

