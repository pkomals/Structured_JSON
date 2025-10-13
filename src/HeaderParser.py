import re
from src.constants.field_aliases import FIELD_ALIASES

class HeaderBasedTableParser:
    def __init__(self, debug=False):
        self.debug = debug
        self.expected_fields = {
            key: [alias.lower() for alias in aliases]
            for key, aliases in FIELD_ALIASES.items()
        }
    
    def normalize_cell(self, cell):
        if isinstance(cell, str):
            cell = cell.strip()
            return cell if cell else None
        return cell
    
    def compress_row(self, row):
        return [self.normalize_cell(cell) for cell in row]
        # return [self.normalize_cell(cell) for cell in row if cell and str(cell).strip()]
    
    def map_headers(self, header_row):
        mapping = {}
        for i, cell in enumerate(header_row):
            if not cell:
                continue
            cell_lower = re.sub(r"[^\w\s]", "", str(cell).lower()).strip()
            for key, aliases in self.expected_fields.items():
                if any(alias in cell_lower for alias in aliases):
                    mapping[key] = i
                    break
        return mapping
    
    
    def parse_single_table(self, table, table_index, inherited_header_mapping=None, current_account=None):
        """Parse a single table and return its transactions"""
        self._current_analysis = None
        rows = table["rows"]
        
        # NEW: Check if this table has nested account structure
        if self._has_nested_account_structure(rows):
            if self.debug:
                print(f"Detected nested account structure in table {table_index}")
            nested_transactions = self._parse_nested_account_table(rows, table_index)
            return nested_transactions, None
        
        # EXISTING: Continue with original logic for normal tables
        transactions = []
        header_found = inherited_header_mapping is not None
        header_mapping = inherited_header_mapping or {}
        found_new_header = None
        
        if self.debug:
            print(f"\nProcessing Table {table_index} with {len(rows)} rows")
            if inherited_header_mapping:
                print(f"Using inherited header: {inherited_header_mapping}")
            if current_account:
                print(f"Current account: {current_account}")
        
        for i, row in enumerate(rows):
            compressed = self.compress_row(row)
            if not compressed or len(compressed) < 3:
                continue
                
            if self.debug:
                print(f"Table {table_index}, Row {i}: {compressed}")
            
            # Look for header row (only if we don't have one yet)
            if not header_found and len(compressed) >= 3:
                header_mapping = self.map_headers(compressed)
                
                # Check for either amount OR debit+credit (common in bank statements)
                has_amount = "amount" in header_mapping
                has_debit_credit = "debit" in header_mapping and "credit" in header_mapping
                
                REQUIRED_FIELDS = {"txn_date", "description"}
                if REQUIRED_FIELDS.issubset(header_mapping.keys()) and (has_amount or has_debit_credit):
                    header_found = True
                    found_new_header = header_mapping
                    if self.debug:
                        # print(f"New header found in Table {table_index}, Row {i}: {header_mapping}")
                        print(f"HEADER ROW {i}: {compressed}")
                        print(f"MAPPING: {header_mapping}")
                        print(f"SAMPLE DATA ROW: {self.compress_row(rows[i+1]) if i+1 < len(rows) else 'N/A'}")
                    continue  # Skip the header row itself
            
            # Process data rows (either after finding header OR using inherited header)
            elif header_found and len(compressed) >= 3:
                clean_row = self.compress_row(row)
                if not clean_row or len(clean_row) < 3:
                    continue  # skip noise
                
                # Skip rows that look like headers (common in multi-page docs)
                if self.looks_like_header(clean_row):
                    if self.debug:
                        print(f"Skipping duplicate header row: {clean_row}")
                    continue
                
                # Skip rows that look like account info or balance summary
                if self.looks_like_account_info(clean_row):
                    if self.debug:
                        print(f"Skipping account info row: {clean_row}")
                    continue
                
                txn = {}
                for field, index in header_mapping.items():
                    if index < len(clean_row):
                        try:
                            txn[field] = self.normalize_cell(clean_row[index])
                        except IndexError:
                            txn[field] = None
                    else:
                        txn[field] = None  # genuine missing field
                if not hasattr(self, '_current_analysis') or self._current_analysis is None:
                    self._current_analysis = self._analyze_column_structure(header_mapping)
                    if self.debug:
                        print(f"Column analysis: {self._current_analysis}")

                # Extract transaction using smart logic
                txn = self._extract_transaction_smart(row, header_mapping, self._current_analysis)
                
                #DEBUG for transactions:
                if self.debug:
                    print(f"Built transaction: {txn}")
                
                # Add account number to transaction if available
                if current_account:
                    txn['account_number'] = current_account
                
                # Only add non-empty transactions (must have date and description)
                if txn.get('txn_date') and txn.get('description'):
                    transactions.append(txn)
                    if self.debug:
                        print(f"Added transaction: {txn}")
        
        if self.debug:
            print(f"Table {table_index} yielded {len(transactions)} transactions")
        
        return transactions, found_new_header

    def looks_like_header(self, row):
        """Check if a row looks like a header (to skip duplicate headers on subsequent pages)"""
        if not row or len(row) < 3:
            return False
        
        # Convert row to lowercase string for checking
        row_text = " ".join(str(cell).lower() for cell in row if cell)
        
        # Common header indicators
        header_keywords = [
            "date", "transaction", "description", "withdrawal", "deposit", 
            "balance", "credit", "debit", "amount", "details", "chq"
        ]
        
        # If row contains multiple header keywords, it's likely a header
        keyword_count = sum(1 for keyword in header_keywords if keyword in row_text)
        return keyword_count >= 2
    
    def looks_like_account_info(self, row):
        """Check if a row contains account info, opening/closing balance, etc."""
        if not row or len(row) < 2:
            return False
        
        # Convert row to lowercase string for checking
        row_text = " ".join(str(cell).lower() for cell in row if cell)
        
        # Account info indicators
        account_indicators = [
            "opening balance", "closing balance", "account number", 
            "opening", "closing", "balance brought forward", "balance carried forward",
            "account statement for account number"# for multipage statements
        ]
        
        # Check if row contains account-related keywords
        return any(indicator in row_text for indicator in account_indicators)
    
    def find_account_for_table(self, table_index, all_accounts, tables):
        """
        Smart account mapping logic:
        1. If single account found - use for all tables
        2. If multiple accounts - try to map based on table position/content
        """
        if not all_accounts:
            return None
            
        # Single account case - simple
        if len(all_accounts) == 1:
            return all_accounts[0]['account_number']
        
        # Multiple accounts case - need smarter mapping
        # Strategy: Look for account numbers that appear close to this table
        current_table = tables[table_index] if table_index < len(tables) else None
        if not current_table:
            return None
        
        # Check if any account number appears in the current table or nearby tables
        table_text = ""
        for row in current_table.get("rows", []):
            table_text += " ".join(str(cell) for cell in row if cell) + " "
        
        # Also check previous table (often has account header info)
        if table_index > 0:
            prev_table = tables[table_index - 1]
            for row in prev_table.get("rows", []):
                table_text += " ".join(str(cell) for cell in row if cell) + " "
        
        table_text = table_text.lower()
        
        # Find which account number appears in or near this table
        for account in all_accounts:
            acc_num = account['account_number']
            if acc_num and acc_num.lower() in table_text:
                return acc_num
        
        # Fallback: use account based on table position (rough heuristic)
        if table_index < len(all_accounts):
            return all_accounts[table_index]['account_number']
        
        # Last fallback: use the highest confidence account
        return max(all_accounts, key=lambda x: x['confidence'])['account_number']
    
    def parse(self, tables, all_accounts=None):
        """
        Enhanced parse method that uses extracted account numbers
        
        Args:
            tables: List of table data
            all_accounts: List of account dicts from AccountNumberExtractor (optional)
        """
        all_transactions = []
        global_header_mapping = None  # Share header across tables
        
        if self.debug:
            print(f"🚀 Starting to parse {len(tables)} tables")
            if all_accounts:
                print(f"🏦 Available accounts: {[acc['account_number'] for acc in all_accounts]}")
        
        for table_idx, table in enumerate(tables):
            # Determine which account this table belongs to
            current_account = None
            if all_accounts:
                current_account = self.find_account_for_table(table_idx, all_accounts, tables)
            
            # Try to find header in this table, or reuse global header
            table_transactions, found_header = self.parse_single_table(
                table, table_idx, global_header_mapping, current_account
            )
            
            # If we found a header in this table, save it for future tables
            if found_header:
                global_header_mapping = found_header
                if self.debug:
                    print(f"📋 Saved header mapping for subsequent tables: {global_header_mapping}")
            
            all_transactions.extend(table_transactions)
        
        if self.debug:
            print(f"🎯 Total transactions found across all tables: {len(all_transactions)}")
        
        return all_transactions

    # Patch HeaderBasedTableParser class
    def _extract_transaction_smart(self, row, header_mapping, column_analysis):
        """Extract transaction with format-aware logic"""
        txn = {}
        
        # Extract basic fields (same as before)
        for field in ["txn_date", "value_date", "description", "txnId"]:
            if field in header_mapping:
                index = header_mapping[field]
                if index < len(row):
                    txn[field] = self.normalize_cell(row[index])
                else:
                    txn[field] = None
            else:
                txn[field] = None
        
        # Smart amount extraction based on column structure
        if column_analysis["has_separate_debit_credit"]:
            # Separate debit/credit columns
            debit_index = header_mapping.get("debit")
            credit_index = header_mapping.get("credit")
            
            txn["debit"] = self.normalize_cell(row[debit_index]) if debit_index is not None and debit_index < len(row) else None
            txn["credit"] = self.normalize_cell(row[credit_index]) if credit_index is not None and credit_index < len(row) else None
            
        elif column_analysis["has_single_amount"]:
            # Single amount column
            amount_field = column_analysis["amount_column_type"]
            amount_index = header_mapping.get(amount_field)
            
            if amount_index is not None and amount_index < len(row):
                amount_val = self.normalize_cell(row[amount_index])
                
                if amount_field == "debit":
                    txn["debit"] = amount_val
                    txn["credit"] = None
                elif amount_field == "credit":
                    txn["credit"] = amount_val  
                    txn["debit"] = None
                else:  # amount
                    txn["amount"] = amount_val
                    txn["debit"] = None
                    txn["credit"] = None
            else:
                txn["debit"] = None
                txn["credit"] = None
        
        # Extract balance
        if column_analysis.get("balance_column") and column_analysis["balance_column"] in header_mapping:
            balance_index = header_mapping[column_analysis["balance_column"]]
            if balance_index < len(row):
                txn["balance"] = self.normalize_cell(row[balance_index])
            else:
                txn["balance"] = None
        else:
            txn["balance"] = None
        
        return txn

    def _analyze_column_structure(self, header_mapping):
        """
        Analyze the detected column structure to understand the transaction format
        Returns information about how to interpret the columns
        """
        analysis = {
            "has_separate_debit_credit": False,
            "has_single_amount": False,
            "amount_column_type": None,
            "balance_column": None
        }
        
        # Check if we have separate debit/credit columns
        if "debit" in header_mapping and "credit" in header_mapping:
            analysis["has_separate_debit_credit"] = True
        elif "amount" in header_mapping:
            analysis["has_single_amount"] = True
            analysis["amount_column_type"] = "amount"
        elif "debit" in header_mapping and "credit" not in header_mapping:
            # Only debit column - might be a single amount column mislabeled
            analysis["has_single_amount"] = True  
            analysis["amount_column_type"] = "debit"
        elif "credit" in header_mapping and "debit" not in header_mapping:
            # Only credit column - might be a single amount column mislabeled
            analysis["has_single_amount"] = True
            analysis["amount_column_type"] = "credit"
        
        # Find balance column
        if "balance" in header_mapping:
            analysis["balance_column"] = "balance"
        
        return analysis

    def _has_nested_account_structure(self, rows):
        """Detect if table has nested account structure (multiple 'Account Number' rows)"""
        account_count = 0
        for row in rows[:20]:  # Check first 20 rows
            if row and len(row) > 0 and str(row[0]).strip().lower() == 'account number':
                account_count += 1
        return account_count > 1

    def _extract_account_number_from_row(self, row):
        """Extract account number from account header row"""
        if not row or len(row) < 2:
            return None
        
        account_cell = str(row[1]) if row[1] else ""
        # Look for account number pattern (10+ digits)
        match = re.search(r'(\d{10,})', account_cell)
        return match.group(1) if match else None

    def _parse_nested_account_table(self, rows, table_index):
        """Parse table with nested account structure"""
        all_transactions = []
        
        if self.debug:
            print(f"Parsing nested account table {table_index}")
        
        i = 0
        while i < len(rows):
            row = rows[i]
            
            # Look for account number row
            if (row and len(row) > 0 and 
                str(row[0]).strip().lower() == 'account number'):
                
                # Extract account number
                account_num = self._extract_account_number_from_row(row)
                if self.debug:
                    print(f"Found account section: {account_num}")
                
                # Look for header row (should be next row)
                i += 1
                header_row = None
                header_mapping = {}
                
                while i < len(rows):
                    current_row = rows[i]
                    compressed = self.compress_row(current_row)
                    
                    # Stop if we hit another account section
                    if (current_row and len(current_row) > 0 and 
                        str(current_row[0]).strip().lower() == 'account number'):
                        break
                    
                    # Look for header row
                    if not header_mapping and compressed and len(compressed) >= 3:
                        test_mapping = self.map_headers(compressed)
                        has_amount = "amount" in test_mapping
                        has_debit_credit = "debit" in test_mapping and "credit" in test_mapping
                        REQUIRED_FIELDS = {"txn_date", "description"}
                        
                        if REQUIRED_FIELDS.issubset(test_mapping.keys()) and (has_amount or has_debit_credit):
                            header_mapping = test_mapping
                            if self.debug:
                                print(f"  Found header: {header_mapping}")
                            i += 1
                            continue
                    
                    # Process transaction rows
                    if header_mapping and compressed and len(compressed) >= 3:
                        # Skip opening/closing balance rows
                        if (compressed[0] == '' and 'balance' in str(compressed[1]).lower()) or \
                        'closing balance' in str(compressed[0]).lower():
                            if self.debug:
                                print(f"  Skipping balance row: {compressed}")
                            i += 1
                            continue
                        
                        # Build transaction
                        txn = {}
                        print(f"DEBUG Transaction extraction:")
                        print(f"  Original row: {current_row}")
                        print(f"  Compressed row: {compressed}")
                        print(f"  Header mapping: {header_mapping}")
                        for field, index in header_mapping.items():
                            # if index < len(compressed):
                                # txn[field] = self.normalize_cell(compressed[index])
                            if index < len(current_row):
                                txn[field] = self.normalize_cell(current_row[index])
                                
                            else:
                                txn[field] = None
                        
                        # Add account number
                        txn['account_number'] = account_num
                        
                        # Validate transaction (must have date and at least one amount field)
                        has_date = bool(txn.get('txn_date'))
                        has_desc = bool(txn.get('description'))
                        has_amount = bool(txn.get('amount') or txn.get('debit') or txn.get('credit'))
                        
                        if has_date and has_desc and has_amount:
                            all_transactions.append(txn)
                            if self.debug:
                                print(f"  Added transaction: {txn}")
                    
                    i += 1
            else:
                i += 1
        
        return all_transactions
        