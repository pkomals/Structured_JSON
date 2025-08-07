import re
from typing import List, Dict

class SummaryExtractor:
    def __init__(self):
        # Define regex patterns for different fields
        self.patterns = {
            "ifscCode": r"IFSC\s*Code\s*[:\-]?\s*([A-Z]{4}0[0-9A-Z]{6})",
            "micrCode": r"MICR\s*Code\s*[:\-]?\s*(\d{9})",
            "openingDate": r"Opening\s*Date\s*[:\-]?\s*([\d\/\-]+)",
            "maskedAccNumber": r"(?:Account\s*Number|A/C\s*No\.?)\s*[:\-]?\s*(\d{4}[\*\sxX]+[\d]{4})",
            "account_type": r"Account\s*Type\s*[:\-]?\s*([A-Za-z ]+)",
            "branch": r"Branch\s*[:\-]?\s*(.*)",
            "currency": r"Currency\s*[:\-]?\s*([A-Z]{3})",
            "currentBalance": r"(?:Balance|Current\s*Balance)\s*[:\-]?\s*([0-9,]+\.\d{2})",
        }

    def extract(self, pages: List[Dict[str, str]]) -> Dict[str, str]:
        summary = {key: "" for key in [
            "type", "fipId", "branch", "status", "fipName", "currency",
            "facility", "ifscCode", "micrCode", "exchgeRate", "openingDate",
            "account_type", "drawingLimit", "linkedAccRef", "fnrkAccountId",
            "currentBalance", "currentODLimit", "pending_amount",
            "balanceDateTime", "maskedAccNumber", "accountAgeInDays",
            "pending_transactionType"
        ]}

        full_text = "\n".join([p["text"] for p in pages])

        for key, pattern in self.patterns.items():
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                summary[key] = match.group(1).strip()

        return summary
