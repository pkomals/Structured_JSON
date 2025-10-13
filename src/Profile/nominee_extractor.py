from __future__ import annotations
from typing import List, Dict, Any, Optional
import re

class NomineeExtractor:
    """
    Extract nominee information from bank statements.
    Looks for patterns like 'REGISTERED', 'NOT REGISTERED', nominee names, etc.
    """
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        
        # Nominee-related labels
        self.nominee_labels = re.compile(
            r"\b(nominee|nomination|nominate[d]?|beneficiary)\b",
            re.I
        )
        
        # Status patterns
        self.nominee_status = {
            "registered": ["registered", "yes", "available", "done", "completed"],
            "not_registered": ["not registered", "no", "not available", "pending", "not done", "nil"],
            "not_applicable": ["n/a", "na", "not applicable"]
        }
        
        # Name patterns (likely nominee names)
        self.name_pattern = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b")
    
    def extract(self,
                raw_pages: List[Dict[str, Any]],
                tables: Optional[List[Dict[str, Any]]] = None,
                first_n_pages: int = 3,
                name_hint: Optional[str] = None) -> Dict[str, Any]:
        
        if self.debug:
            print("Starting NomineeExtractor...")
        
        # Get text from first few pages
        texts = []
        for page in raw_pages[:first_n_pages]:
            text = page.get("text", "") or ""
            texts.append(text)
        
        full_text = "\n".join(texts)
        
        # 1. Try labeled extraction from text
        result = self._extract_from_labeled_text(full_text, name_hint)
        if result:
            return result
        
        # 2. Try table extraction
        if tables:
            result = self._extract_from_tables(tables, name_hint)
            if result:
                return result
        
        # 3. Try pattern matching
        result = self._extract_from_patterns(full_text, name_hint)
        if result:
            return result
        
        return {"nominee": None, "confidence": 0.0, "evidence": None}
    
    def _extract_from_labeled_text(self, text: str, name_hint: Optional[str]) -> Optional[Dict[str, Any]]:
        """Extract from labeled text like 'Nominee: REGISTERED' or 'Nominee: John Doe'"""
        for match in self.nominee_labels.finditer(text):
            # Look on same line
            line_start = text.rfind("\n", 0, match.start())
            line_end = text.find("\n", match.end())
            if line_start == -1: line_start = 0
            if line_end == -1: line_end = len(text)
            
            line = text[line_start:line_end]
            
            # Extract after the label
            after_label = line[match.end() - line_start:].strip()
            after_label = re.sub(r"^[:\-\s]+", "", after_label)  # Remove colons, dashes, spaces
            
            nominee = self._identify_nominee(after_label, name_hint)
            if nominee:
                if self.debug:
                    print(f"Found labeled nominee: {nominee} in line: {line}")
                return {
                    "nominee": nominee,
                    "confidence": 0.9,
                    "evidence": "text labeled (same line)"
                }
            
            # Check next line
            next_line_start = line_end + 1
            if next_line_start < len(text):
                next_line_end = text.find("\n", next_line_start)
                if next_line_end == -1: next_line_end = len(text)
                next_line = text[next_line_start:next_line_end].strip()
                
                nominee = self._identify_nominee(next_line, name_hint)
                if nominee:
                    if self.debug:
                        print(f"Found labeled nominee: {nominee} in next line: {next_line}")
                    return {
                        "nominee": nominee,
                        "confidence": 0.85,
                        "evidence": "text labeled (next line)"
                    }
        
        return None
    
    def _extract_from_tables(self, tables: List[Dict[str, Any]], name_hint: Optional[str]) -> Optional[Dict[str, Any]]:
        """Extract from table structures"""
        for table in tables[:3]:  # Check first 3 tables
            rows = table.get("rows", [])
            
            # Check for right-cell pattern
            for row in rows:
                for i, cell in enumerate(row):
                    if not isinstance(cell, str):
                        continue
                    
                    if self.nominee_labels.search(cell):
                        # Check right cell
                        if i + 1 < len(row) and isinstance(row[i + 1], str):
                            nominee = self._identify_nominee(row[i + 1], name_hint)
                            if nominee:
                                if self.debug:
                                    print(f"Found nominee in table right cell: {nominee}")
                                return {
                                    "nominee": nominee,
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
                    
                    if self.nominee_labels.search(cell):
                        # Check below cell
                        if j < len(next_row) and isinstance(next_row[j], str):
                            nominee = self._identify_nominee(next_row[j], name_hint)
                            if nominee:
                                if self.debug:
                                    print(f"Found nominee in table below cell: {nominee}")
                                return {
                                    "nominee": nominee,
                                    "confidence": 0.8,
                                    "evidence": "table below cell"
                                }
        
        return None
    
    def _extract_from_patterns(self, text: str, name_hint: Optional[str]) -> Optional[Dict[str, Any]]:
        """General pattern matching for nominee information"""
        # Look for common nominee patterns
        patterns = [
            r"nominee\s*[:\-]?\s*([a-z\s]+(?:registered|not registered))",
            r"nomination\s*[:\-]?\s*([a-z\s]+(?:registered|not registered|done|pending))",
            r"beneficiary\s*[:\-]?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)"
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.I)
            for match in matches:
                nominee = self._identify_nominee(match.group(1), name_hint)
                if nominee:
                    if self.debug:
                        print(f"Found nominee via pattern: {nominee}")
                    return {
                        "nominee": nominee,
                        "confidence": 0.7,
                        "evidence": "pattern matching"
                    }
        
        return None
    
    def _identify_nominee(self, text: str, name_hint: Optional[str]) -> Optional[str]:
        """Identify nominee from text - could be status or name"""
        if not text:
            return None
        
        text_clean = text.strip()
        text_lower = text_clean.lower()
        
        # Check for status keywords first
        for status, aliases in self.nominee_status.items():
            for alias in aliases:
                if alias in text_lower:
                    return status
        
        # Check if it looks like a person's name
        if self._looks_like_name(text_clean, name_hint):
            return text_clean
        
        # If text has reasonable length and contains letters, might be a name
        if len(text_clean) > 3 and re.search(r"[A-Za-z]", text_clean):
            # Avoid obvious non-names
            if not re.search(r"(account|number|\d{6,}|branch|ifsc)", text_lower):
                return text_clean
        
        return None
    
    def _looks_like_name(self, text: str, name_hint: Optional[str]) -> bool:
        """Check if text looks like a person's name"""
        if not text:
            return False
        
        # If it matches the account holder's name pattern, likely not nominee
        if name_hint and name_hint.lower() in text.lower():
            return False
        
        # Check if it matches name patterns
        if self.name_pattern.fullmatch(text.strip()):
            return True
        
        # Check for common name characteristics
        words = text.strip().split()
        if len(words) >= 2 and all(word.isalpha() and word[0].isupper() for word in words):
            return True
        
        return False