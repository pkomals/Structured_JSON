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
