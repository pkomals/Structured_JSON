import fitz
import re
import pdfplumber

class PDFTextExtractor:
    def __init__(self, pdf_path: str, password: str = None):
        self.pdf_path = pdf_path
        self.password = password

    
    def extractor(self):
        doc = fitz.open(self.pdf_path)
        if self.password:
            doc.authenticate(self.password)
        pages = []
        for i, page in enumerate(doc):
            text = page.get_text("text")
            pages.append(
                {
                    "page_no": i + 1,
                    "text": text.strip()

                }
            )
        return pages
    
# class TableDetector:
#     def __init__(self, txt_json):
#          # Semantic header keywords → known variants
#         self.header_keywords = {
#             "date": ["date", "txn date", "transaction date", "trxn dt"],
#             "value_date": ["value date", "val date", "val dt"],
#             "description": ["description", "narration", "details", "particulars"],
#             "ref": ["ref", "ref no", "cheque", "instrument no"],
#             "debit": ["debit", "dr"],
#             "credit": ["credit", "cr"],
#             "balance": ["balance", "bal", "closing balance", "cl bal"]
#         }
#     def is_header_line(self,line:str)->bool:
#         line_clean=re.sub(r"[^a-zA-Z0-9\s]","",line.lower())
#         tokens=set(line_clean.split()) 
#         match_count=0

#         for variants in self.header_keywords.values():
#             if any(v.replace(" ","")in "".join(tokens) for v in variants):
#                 match_count=+1

#         return match_count>=3
    
#     def is_table_row(self,line:str)->bool:
#         return len(re.findall(r"\d[\d,]*\.\d{2}",line))>=2
    
#     def is_footer_line(self,line:str)->bool:
#         # using common end-of-table indicators
#         lower=line.lower()
#         return any(kw in lower for kw in ["closing balance", "summary", "total", "thank you", "signature", "end of"])
    
#     def extract_table_lines(self,text:str)->list:
#         lines=text.splitlines()
#         in_table=False
#         table_lines=[]
#         non_match_count=0
#         max_non_rows=5 # allow 5 noicy lines before stopping


#         for line in lines:
#             if not in_table and self.is_header_line(line):
#                 in_table=True
#                 continue # skip header

#             if in_table:
#                 if self.is_footer_line(line):
#                     break

#                 if self.is_table_row(line):
#                     table_lines.append(line.strip())
#                     non_match_count=0

#                 else:
#                     non_match_count+=1
#                     if non_match_count>=max_non_rows:
#                         break
#         return table_lines


class PlumberTableExtractor:
    def __init__(self, pdf_path: str, password: str = None):
        self.pdf_path = pdf_path
        self.password = password

    def extract_tables(self):
        all_tables = []

        with pdfplumber.open(self.pdf_path, password=self.password) as pdf:
            for i, page in enumerate(pdf.pages):
                tables = page.extract_tables()
                for table in tables:
                    if table and len(table) > 1:  # has header + at least 1 row
                        all_tables.append({
                            "page_number": i + 1,
                            "rows": table
                        })

        return all_tables
