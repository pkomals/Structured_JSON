from __future__ import annotations
from typing import List, Dict, Any, Optional
import re

class SummaryExtractor:
    """
    Extract summary information from bank statements.
    Combines already extracted fields with new fields like branch, currency, IFSC, MICR.
    """
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        
        # Branch-related labels
        self.branch_labels = re.compile(
            r"\b(branch|branch\s*name|branch\s*office|office|location)\b",
            re.I
        )
        
        # Currency patterns
        self.currency_pattern = re.compile(r"\b(INR|USD|EUR|GBP|AUD|CAD)\b", re.I)
        
        # IFSC patterns
        self.ifsc_pattern = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")
        
        # MICR patterns  
        self.micr_pattern = re.compile(r"\b\d{9}\b")
        
        # Labels for IFSC and MICR
        self.ifsc_labels = re.compile(r"\b(ifsc|ifsc\s*code|swift\s*code)\b", re.I)
        self.micr_labels = re.compile(r"\b(micr|micr\s*code)\b", re.I)
    
    def extract(self,
                raw_pages: List[Dict[str, Any]],
                tables: Optional[List[Dict[str, Any]]] = None,
                first_n_pages: int = 3,
                existing_profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        
        if self.debug:
            print("Starting SummaryExtractor...")
        
        # Get text from first few pages
        texts = []
        for page in raw_pages[:first_n_pages]:
            text = page.get("text", "") or ""
            texts.append(text)
        
        full_text = "\n".join(texts)
        
        # Start with existing profile data
        summary = {
            "type": existing_profile.get("type") if existing_profile else None,
            "fipId": None,  # Keep as None per requirement
            "branch": None,
            "status": None,  # Keep as None per requirement
            "currency": None,
            "ifscCode": None,
            "micrCode": None,
            "account_type": existing_profile.get("account_type") if existing_profile else None,
            "maskedAccNumber": existing_profile.get("maskedAccNumber")[0] if existing_profile and existing_profile.get("maskedAccNumber") else None
        }
        
        # Extract new fields
        branch = self._extract_branch(full_text, tables)
        if branch:
            summary["branch"] = branch
        
        currency = self._extract_currency(full_text, tables)
        if currency:
            summary["currency"] = currency
        
        ifsc_code = self._extract_ifsc(full_text, tables)
        if ifsc_code:
            summary["ifscCode"] = ifsc_code
        
        micr_code = self._extract_micr(full_text, tables)
        if micr_code:
            summary["micrCode"] = micr_code
        
        return summary
    
    def _extract_branch(self, text: str, tables: Optional[List[Dict[str, Any]]]) -> Optional[str]:
        """Extract branch information"""
        
        # 1. Try labeled text extraction
        for match in self.branch_labels.finditer(text):
            line_start = text.rfind("\n", 0, match.start())
            line_end = text.find("\n", match.end())
            if line_start == -1: line_start = 0
            if line_end == -1: line_end = len(text)
            
            line = text[line_start:line_end]
            
            # Extract after the label
            after_label = line[match.end() - line_start:].strip()
            after_label = re.sub(r"^[:\-\s]+", "", after_label)
            
            if after_label and len(after_label) > 3:
                # Clean up common artifacts
                branch_name = re.sub(r"(cid:\d+|\(INR\))", "", after_label).strip()
                if len(branch_name) > 3:
                    if self.debug:
                        print(f"Found branch via labeled text: {branch_name}")
                    return branch_name
        
        # 2. Try table extraction
        if tables:
            for table in tables[:3]:
                rows = table.get("rows", [])
                
                # Right-cell pattern
                for row in rows:
                    for i, cell in enumerate(row):
                        if not isinstance(cell, str):
                            continue
                        
                        if self.branch_labels.search(cell):
                            if i + 1 < len(row) and isinstance(row[i + 1], str):
                                branch_candidate = row[i + 1].strip()
                                if len(branch_candidate) > 3:
                                    if self.debug:
                                        print(f"Found branch via table right cell: {branch_candidate}")
                                    return branch_candidate
        
        return None
    
    def _extract_currency(self, text: str, tables: Optional[List[Dict[str, Any]]]) -> Optional[str]:
        """Extract currency information"""
        
        # Look for currency patterns in text
        currency_matches = self.currency_pattern.findall(text)
        if currency_matches:
            # Return the most common currency found
            currency = max(set(currency_matches), key=currency_matches.count)
            if self.debug:
                print(f"Found currency: {currency}")
            return currency.upper()
        
        # Check tables for currency info
        if tables:
            for table in tables[:3]:
                rows = table.get("rows", [])
                for row in rows:
                    for cell in row:
                        if isinstance(cell, str):
                            currency_match = self.currency_pattern.search(cell)
                            if currency_match:
                                if self.debug:
                                    print(f"Found currency in table: {currency_match.group(0)}")
                                return currency_match.group(0).upper()
        
        return None
    
    def _extract_ifsc(self, text: str, tables: Optional[List[Dict[str, Any]]]) -> Optional[str]:
        """Extract IFSC code"""
        
        # 1. Try labeled extraction
        for match in self.ifsc_labels.finditer(text):
            line_start = text.rfind("\n", 0, match.start())
            line_end = text.find("\n", match.end())
            if line_start == -1: line_start = 0
            if line_end == -1: line_end = len(text)
            
            line = text[line_start:line_end]
            
            # Look for IFSC pattern in the same line
            ifsc_match = self.ifsc_pattern.search(line)
            if ifsc_match:
                if self.debug:
                    print(f"Found IFSC via labeled text: {ifsc_match.group(0)}")
                return ifsc_match.group(0)
        
        # 2. Try pattern matching across text
        ifsc_matches = self.ifsc_pattern.findall(text)
        if ifsc_matches:
            if self.debug:
                print(f"Found IFSC via pattern: {ifsc_matches[0]}")
            return ifsc_matches[0]
        
        # 3. Try table extraction
        if tables:
            for table in tables[:3]:
                rows = table.get("rows", [])
                
                for row in rows:
                    for i, cell in enumerate(row):
                        if not isinstance(cell, str):
                            continue
                        
                        # Check if this cell has IFSC label
                        if self.ifsc_labels.search(cell):
                            # Check right cell
                            if i + 1 < len(row) and isinstance(row[i + 1], str):
                                ifsc_match = self.ifsc_pattern.search(row[i + 1])
                                if ifsc_match:
                                    if self.debug:
                                        print(f"Found IFSC via table: {ifsc_match.group(0)}")
                                    return ifsc_match.group(0)
                        
                        # Check if this cell contains IFSC code directly
                        ifsc_match = self.ifsc_pattern.search(cell)
                        if ifsc_match:
                            if self.debug:
                                print(f"Found IFSC in table cell: {ifsc_match.group(0)}")
                            return ifsc_match.group(0)
        
        return None
    
    def _extract_micr(self, text: str, tables: Optional[List[Dict[str, Any]]]) -> Optional[str]:
        """Extract MICR code"""
        
        # 1. Try labeled extraction
        for match in self.micr_labels.finditer(text):
            line_start = text.rfind("\n", 0, match.start())
            line_end = text.find("\n", match.end())
            if line_start == -1: line_start = 0
            if line_end == -1: line_end = len(text)
            
            line = text[line_start:line_end]
            
            # Look for MICR pattern in the same line
            micr_match = self.micr_pattern.search(line)
            if micr_match:
                if self.debug:
                    print(f"Found MICR via labeled text: {micr_match.group(0)}")
                return micr_match.group(0)
        
        # 2. Try table extraction
        if tables:
            for table in tables[:3]:
                rows = table.get("rows", [])
                
                for row in rows:
                    for i, cell in enumerate(row):
                        if not isinstance(cell, str):
                            continue
                        
                        # Check if this cell has MICR label
                        if self.micr_labels.search(cell):
                            # Check right cell
                            if i + 1 < len(row) and isinstance(row[i + 1], str):
                                micr_match = self.micr_pattern.search(row[i + 1])
                                if micr_match:
                                    if self.debug:
                                        print(f"Found MICR via table: {micr_match.group(0)}")
                                    return micr_match.group(0)
        
        # 3. Pattern matching (but be careful not to pick up account numbers)
        micr_candidates = self.micr_pattern.findall(text)
        if micr_candidates:
            # Filter out likely account numbers (they're usually longer or have context)
            for candidate in micr_candidates:
                # Look at context around the number
                candidate_index = text.find(candidate)
                context_start = max(0, candidate_index - 20)
                context_end = min(len(text), candidate_index + len(candidate) + 20)
                context = text[context_start:context_end].lower()
                
                # If context suggests it's MICR (not account number)
                if any(word in context for word in ["micr", "code", "branch"]):
                    if self.debug:
                        print(f"Found MICR via pattern with context: {candidate}")
                    return candidate
        
        return None