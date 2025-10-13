from __future__ import annotations
from typing import List, Dict, Any, Optional
import re

class AccountTypeExtractor:
    """
    Extract account type information from bank statements.
    Looks for patterns like 'SAVINGS', 'CURRENT', 'DEPOSIT', etc.
    """
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        
        # Account type patterns
        self.account_type_labels = re.compile(
            r"\b(account\s*type|type\s*of\s*account|a\/c\s*type|account\s*category)\b",
            re.I
        )
        
        # Common account types
        self.account_types = {
            "savings": ["savings", "sb", "saving"],
            "current": ["current", "ca", "cur"],
            "deposit": ["deposit", "fd", "fixed deposit", "term deposit", "sugam deposit"],
            "loan": ["loan", "credit", "overdraft", "od"],
            "nri": ["nri", "non resident", "nonresident"],
            "salary": ["salary", "sal"],
            "joint": ["joint", "jt"]
        }
    
    def extract(self,
                raw_pages: List[Dict[str, Any]],
                tables: Optional[List[Dict[str, Any]]] = None,
                first_n_pages: int = 3) -> Dict[str, Any]:
        
        if self.debug:
            print("Starting AccountTypeExtractor...")
        
        # Get text from first few pages
        texts = []
        for page in raw_pages[:first_n_pages]:
            text = page.get("text", "") or ""
            texts.append(text)
        
        full_text = "\n".join(texts)
        
        # 1. Try labeled extraction from text
        result = self._extract_from_labeled_text(full_text)
        if result:
            return result
        
        # 2. Try table extraction
        if tables:
            result = self._extract_from_tables(tables)
            if result:
                return result
        
        # 3. Try pattern matching in account number lines
        result = self._extract_from_account_lines(full_text)
        if result:
            return result
        
        # 4. Try general pattern matching
        result = self._extract_from_patterns(full_text)
        if result:
            return result
        
        return {"account_type": None, "confidence": 0.0, "evidence": None}
    
    def _extract_from_labeled_text(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract from labeled text like 'Account Type: SAVINGS'"""
        for match in self.account_type_labels.finditer(text):
            # Look for account type on same line
            line_start = text.rfind("\n", 0, match.start())
            line_end = text.find("\n", match.end())
            if line_start == -1: line_start = 0
            if line_end == -1: line_end = len(text)
            
            line = text[line_start:line_end]
            
            # Extract after the label
            after_label = line[match.end() - line_start:].strip()
            account_type = self._identify_account_type(after_label)
            if account_type:
                if self.debug:
                    print(f"Found labeled account type: {account_type} in line: {line}")
                return {
                    "account_type": account_type,
                    "confidence": 0.9,
                    "evidence": "text labeled (same line)"
                }
            
            # Check next line
            next_line_start = line_end + 1
            if next_line_start < len(text):
                next_line_end = text.find("\n", next_line_start)
                if next_line_end == -1: next_line_end = len(text)
                next_line = text[next_line_start:next_line_end].strip()
                
                account_type = self._identify_account_type(next_line)
                if account_type:
                    if self.debug:
                        print(f"Found labeled account type: {account_type} in next line: {next_line}")
                    return {
                        "account_type": account_type,
                        "confidence": 0.85,
                        "evidence": "text labeled (next line)"
                    }
        
        return None
    
    def _extract_from_tables(self, tables: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Extract from table structures"""
        for table in tables[:3]:  # Check first 3 tables
            rows = table.get("rows", [])
            
            # Check for right-cell pattern
            for row in rows:
                for i, cell in enumerate(row):
                    if not isinstance(cell, str):
                        continue
                    
                    if self.account_type_labels.search(cell):
                        # Check right cell
                        if i + 1 < len(row) and isinstance(row[i + 1], str):
                            account_type = self._identify_account_type(row[i + 1])
                            if account_type:
                                if self.debug:
                                    print(f"Found account type in table right cell: {account_type}")
                                return {
                                    "account_type": account_type,
                                    "confidence": 0.85,
                                    "evidence": "table right cell"
                                }
            
            # Check for below-cell pattern
            for i in range(len(rows) - 1):
                row = rows[i]
                next_row = rows[i + 1]
                
                for j, cell in enumerate(row):
                    if not isinstance(cell, str):
                        continue
                    
                    if self.account_type_labels.search(cell):
                        # Check below cell
                        if j < len(next_row) and isinstance(next_row[j], str):
                            account_type = self._identify_account_type(next_row[j])
                            if account_type:
                                if self.debug:
                                    print(f"Found account type in table below cell: {account_type}")
                                return {
                                    "account_type": account_type,
                                    "confidence": 0.8,
                                    "evidence": "table below cell"
                                }
        
        return None
    
    def _extract_from_account_lines(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract from lines containing account information"""
        lines = text.split("\n")
        
        for line in lines:
            # Look for lines with account numbers that might contain type info
            if re.search(r"\b\d{10,}\b", line):  # Has account-like number
                account_type = self._identify_account_type(line)
                if account_type:
                    if self.debug:
                        print(f"Found account type in account line: {account_type}")
                    return {
                        "account_type": account_type,
                        "confidence": 0.75,
                        "evidence": "account line pattern"
                    }
        
        return None
    
    def _extract_from_patterns(self, text: str) -> Optional[Dict[str, Any]]:
        """General pattern matching across text"""
        # Look for common patterns in parentheses
        patterns = [
            r"\(([^)]*(?:savings|current|deposit|fd)[^)]*)\)",
            r"([A-Z\s]+(?:SAVINGS|CURRENT|DEPOSIT)[A-Z\s]*)",
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.I)
            for match in matches:
                account_type = self._identify_account_type(match.group(1))
                if account_type:
                    if self.debug:
                        print(f"Found account type via pattern: {account_type}")
                    return {
                        "account_type": account_type,
                        "confidence": 0.7,
                        "evidence": "pattern matching"
                    }
        
        return None
    
    def _identify_account_type(self, text: str) -> Optional[str]:
        """Identify account type from text"""
        if not text:
            return None
        
        text_clean = re.sub(r"[^\w\s]", "", text.lower()).strip()
        
        for account_type, aliases in self.account_types.items():
            for alias in aliases:
                if alias in text_clean:
                    return account_type
        
        return None