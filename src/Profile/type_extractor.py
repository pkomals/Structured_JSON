from __future__ import annotations
from typing import List, Dict, Any, Optional
import re

class TypeExtractor:
    """
    Extract account holder type information from bank statements.
    Looks for patterns like 'SINGLE', 'JOINT', 'INDIVIDUAL', etc.
    """
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        
        # Type-related labels
        self.type_labels = re.compile(
            r"\b(type|account\s*holder\s*type|holder\s*type|ownership\s*type|account\s*mode)\b",
            re.I
        )
        
        # Account holder types
        self.holder_types = {
            "single": ["single", "individual", "sole", "single holder"],
            "joint": ["joint", "joint holder", "jt", "jointly"],
            "minor": ["minor", "guardian", "child"],
            "corporate": ["corporate", "company", "business", "firm"],
            "trust": ["trust", "trustee"],
            "society": ["society", "association", "club"]
        }
        
        # Patterns that might indicate joint accounts
        self.joint_indicators = re.compile(r"\b(and|&|\+|jointly|joint)\b", re.I)
    
    def extract(self,
                raw_pages: List[Dict[str, Any]],
                tables: Optional[List[Dict[str, Any]]] = None,
                first_n_pages: int = 3,
                name_hint: Optional[str] = None) -> Dict[str, Any]:
        
        if self.debug:
            print("Starting TypeExtractor...")
        
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
        
        # 3. Try name-based inference
        if name_hint:
            result = self._extract_from_name_pattern(name_hint, full_text)
            if result:
                return result
        
        # 4. Try pattern matching
        result = self._extract_from_patterns(full_text)
        if result:
            return result
        
        return {"type": None, "confidence": 0.0, "evidence": None}
    
    def _extract_from_labeled_text(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract from labeled text like 'Type: SINGLE' or 'Account Holder Type: JOINT'"""
        for match in self.type_labels.finditer(text):
            # Look on same line
            line_start = text.rfind("\n", 0, match.start())
            line_end = text.find("\n", match.end())
            if line_start == -1: line_start = 0
            if line_end == -1: line_end = len(text)
            
            line = text[line_start:line_end]
            
            # Extract after the label
            after_label = line[match.end() - line_start:].strip()
            after_label = re.sub(r"^[:\-\s]+", "", after_label)  # Remove colons, dashes, spaces
            
            holder_type = self._identify_type(after_label)
            if holder_type:
                if self.debug:
                    print(f"Found labeled type: {holder_type} in line: {line}")
                return {
                    "type": holder_type,
                    "confidence": 0.9,
                    "evidence": "text labeled (same line)"
                }
            
            # Check next line
            next_line_start = line_end + 1
            if next_line_start < len(text):
                next_line_end = text.find("\n", next_line_start)
                if next_line_end == -1: next_line_end = len(text)
                next_line = text[next_line_start:next_line_end].strip()
                
                holder_type = self._identify_type(next_line)
                if holder_type:
                    if self.debug:
                        print(f"Found labeled type: {holder_type} in next line: {next_line}")
                    return {
                        "type": holder_type,
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
                    
                    if self.type_labels.search(cell):
                        # Check right cell
                        if i + 1 < len(row) and isinstance(row[i + 1], str):
                            holder_type = self._identify_type(row[i + 1])
                            if holder_type:
                                if self.debug:
                                    print(f"Found type in table right cell: {holder_type}")
                                return {
                                    "type": holder_type,
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
                    
                    if self.type_labels.search(cell):
                        # Check below cell
                        if j < len(next_row) and isinstance(next_row[j], str):
                            holder_type = self._identify_type(next_row[j])
                            if holder_type:
                                if self.debug:
                                    print(f"Found type in table below cell: {holder_type}")
                                return {
                                    "type": holder_type,
                                    "confidence": 0.8,
                                    "evidence": "table below cell"
                                }
        
        return None
    
    def _extract_from_name_pattern(self, name: str, full_text: str) -> Optional[Dict[str, Any]]:
        """Infer type from name patterns"""
        if not name:
            return None
        
        name_clean = name.strip()
        
        # Check if name suggests joint account
        if self.joint_indicators.search(name_clean):
            if self.debug:
                print(f"Inferred joint account from name pattern: {name_clean}")
            return {
                "type": "joint",
                "confidence": 0.7,
                "evidence": "name pattern analysis"
            }
        
        # Check if multiple names appear in the document (suggesting joint)
        name_parts = re.split(r"\s+and\s+|\s+&\s+", name_clean, flags=re.I)
        if len(name_parts) > 1:
            if self.debug:
                print(f"Multiple names detected: {name_parts}")
            return {
                "type": "joint", 
                "confidence": 0.75,
                "evidence": "multiple names detected"
            }
        
        return None
    
    def _extract_from_patterns(self, text: str) -> Optional[Dict[str, Any]]:
        """General pattern matching for type information"""
        # Look for common type patterns
        patterns = [
            r"\b(single|individual|sole)\s+holder\b",
            r"\b(joint|jointly)\s+held\b",
            r"\bholder[s]?\s*[:\-]?\s*(single|joint|individual)",
            r"\baccount\s+mode\s*[:\-]?\s*(single|joint)"
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.I)
            for match in matches:
                holder_type = self._identify_type(match.group(0))
                if holder_type:
                    if self.debug:
                        print(f"Found type via pattern: {holder_type}")
                    return {
                        "type": holder_type,
                        "confidence": 0.7,
                        "evidence": "pattern matching"
                    }
        
        return None
    
    def _identify_type(self, text: str) -> Optional[str]:
        """Identify holder type from text"""
        if not text:
            return None
        
        text_clean = re.sub(r"[^\w\s]", "", text.lower()).strip()
        
        for holder_type, aliases in self.holder_types.items():
            for alias in aliases:
                if alias in text_clean:
                    return holder_type
        
        return None