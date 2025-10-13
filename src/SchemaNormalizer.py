from typing import List, Dict, Union
from datetime import datetime

class SchemaNormalizer:
    def __init__(self, profile_accounts=None):
        """
        profile_accounts: List of account numbers extracted from profile section
        """
        self.profile_accounts = profile_accounts or []

    def normalize_transactions(self, transactions: List[Dict[str, Union[str, float]]],profile_accounts=None) -> List[Dict[str, Union[str, float]]]:
        """
        profile_accounts: Can be passed here as well to override constructor
        
        """
        # Use parameter if provided, otherwise use instance variable
        available_accounts = profile_accounts or self.profile_accounts
        normalized = []

        for txn in transactions:
            
            amount = ""
            txn_type = ""
            debit_val = txn.get("debit")
            credit_val = txn.get("credit")
          
            debit_amount = self._clean_amount(debit_val) if debit_val else 0
            credit_amount = self._clean_amount(credit_val) if credit_val else 0
            
            if debit_amount and debit_amount > 0:
                amount = debit_amount
                txn_type = "debit"
            elif credit_amount and credit_amount > 0:
                amount = credit_amount
                txn_type = "credit"
            # Normalize date
            value_date = self._normalize_date(txn.get("txn_date", ""))

            # Clean balance
            balance = self._clean_amount(txn.get("balance", ""))

            # account no. from txn/profile
            account_number = self._get_account_number(txn, available_accounts)

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
                "maskedAccNumber": account_number,
                "transactionTimestamp": ""  # can be mapped from txn.get("txn_date") if needed
            })

        return normalized

    def _clean_amount(self, val: Union[str, float]) -> Union[float, str]:
        try:
            return float(str(val).replace(",", "").strip())
        except:
            return ""

    def _normalize_date(self, date_str: str) -> str:
       
        date_str = date_str.strip()
        #datetime formats (for Excel timestamps)
        datetime_formats = [
        "%Y-%m-%d %H:%M:%S",    # 2025-03-28 00:00:00
        "%Y-%m-%d",             # 2025-03-28
        "%Y/%m/%d %H:%M:%S",    # 2025/03/28 00:00:00
        "%Y/%m/%d"              # 2025/03/28
        ]
        for fmt in datetime_formats:
            try:
                return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
            except:
                continue
        # Existing pdf date fomats       
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d %b '%y", "%d %b %Y", "%d-%b-%Y", "%d/%m/%y", "%m/%d/%y", "%d-%b-%y"):
            try:
                parsed_date = datetime.strptime(date_str, fmt)
                result = parsed_date.strftime("%Y-%m-%d")
                # print(f"DEBUG: Successfully parsed '{date_str}' with format '{fmt}' -> '{result}'")
                return result
                # return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
            except:
                continue
        print(f"DEBUG: Failed to parse date '{date_str}' with any format")
        return ""
    
    def _get_account_number(self, txn: Dict, available_accounts: List[str]) -> str:
        """
        Account number fallback logic:
        1. Use transaction's account_number if available
        2. Use first account from profile if single account
        3. Return empty string if no accounts (ambiguous)
        """
        # Case 1: Transaction has its own account number (nested structure)
        if txn.get("account_number"):
            return str(txn["account_number"])
        
        # Case 2: Use profile accounts as fallback
        if available_accounts:
            if len(available_accounts) == 1:
                # Single account - safe to use
                return str(available_accounts[0])
            elif len(available_accounts) > 1:
                # Multiple accounts - ambiguous, return empty
                # Could also implement logic to guess based on transaction amount/type
                return ""
        
        # Case 3: No account info available
        return ""
