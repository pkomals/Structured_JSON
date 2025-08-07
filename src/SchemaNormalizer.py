from typing import List, Dict, Union
from datetime import datetime

class SchemaNormalizer:
    def normalize_transactions(self, transactions: List[Dict[str, Union[str, float]]]) -> List[Dict[str, Union[str, float]]]:
        normalized = []

        for txn in transactions:
            # Determine amount and type
            amount = ""
            txn_type = ""
            if txn.get("debit"):
                amount = self._clean_amount(txn["debit"])
                txn_type = "debit"
            elif txn.get("credit"):
                amount = self._clean_amount(txn["credit"])
                txn_type = "credit"

            # Normalize date
            value_date = self._normalize_date(txn.get("txn_date", ""))

            # Clean balance
            balance = self._clean_amount(txn.get("balance", ""))

            # Append normalized record
            normalized.append({
                "mode": "",  # not derivable from raw
                "type": txn_type,
                "fipId": "",
                "txnId": "",
                "amount": amount,
                "narration": txn.get("description", ""),
                "reference": txn.get("ref_no", ""),
                "valueDate": value_date,
                "account_type": "",
                "linkedAccRef": "",
                "fnrkAccountId": "",
                "currentBalance": balance,
                "maskedAccNumber": "",
                "transactionTimestamp": ""  # can be mapped from txn.get("txn_date") if needed
            })

        return normalized

    def _clean_amount(self, val: Union[str, float]) -> Union[float, str]:
        try:
            return float(str(val).replace(",", "").strip())
        except:
            return ""

    def _normalize_date(self, date_str: str) -> str:
        """Attempt to parse date in formats like '05/10/2024' or '5 Oct 2024'."""
        date_str = date_str.strip()
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d %b '%y", "%d %b %Y"):
            try:
                return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
            except:
                continue
        return ""
