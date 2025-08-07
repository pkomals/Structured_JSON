import re
from src.constants.field_aliases import FIELD_ALIASES

class HeaderBasedTableParser:
    def __init__(self):
        self.expected_fields = {
            key: [alias.lower() for alias in aliases]
            for key, aliases in FIELD_ALIASES.items()
        }
    
    def normalize_cell(self,cell):
        if isinstance(cell,str):
            cell=cell.strip()
            return cell if cell else None
        return cell
    
    def compress_row(self,row):
        return [self.normalize_cell(cell) for cell in row if cell and str(cell).strip()]
    
    
    def map_headers(self,header_row):
        mapping={}
        for i, cell in enumerate(header_row):
            if not cell:
                continue
            # cell_lower=str(cell).strip().lower()
            cell_lower=re.sub(r"[^\w\s]", "",str(cell).lower()).strip()
            for key, aliases in self.expected_fields.items():
                if any (alias in cell_lower for alias in aliases):
                    mapping[key]=i
                    break
        return mapping
    
    def parse(self,tables):
        transactions=[]
        for table in tables:
            rows=table["rows"]
            header_found=False
            header_mapping={}
            # print("Scanning table Rows...")
            for i, row in enumerate(rows):
                compressed=self.compress_row(row)
                if not compressed or len(compressed) < 3:
                    continue
                print(f"🔹 Row {i}: {compressed}")
                if not header_found and len(compressed)>=3:
                    header_mapping=self.map_headers(compressed)
                    # print("🔎 Header mapping:", header_mapping)
                    # Check for either amount OR debit+credit (common in bank statements)
                    has_amount = "amount" in header_mapping
                    has_debit_credit = "debit" in header_mapping and "credit" in header_mapping
                    
                    REQUIRED_FIELDS = {"txn_date", "description"}
                    if REQUIRED_FIELDS.issubset(header_mapping.keys()) and (has_amount or has_debit_credit):
                        header_found = True
                elif header_found:
                    clean_row= self.compress_row(row)
                    if not clean_row or len(clean_row)<3:
                        continue # skip noice

                    txn={}
                    for field, index in header_mapping.items():
                        if index<len(row):
                            try:
                                txn[field]=self.normalize_cell(clean_row[index])
                            except IndexError:
                                txn[field]=None
                        else:
                            txn[field]=None  # genuine missing field
                    transactions.append(txn)
        return transactions



