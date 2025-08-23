import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, List

from src.PDFTextExtractor import PlumberTableExtractor, PDFTextExtractor
from src.HeaderParser import HeaderBasedTableParser
from src.SchemaNormalizer import SchemaNormalizer
from src.SummaryExtractor import SummaryExtractor
from src.assembler import BankStatementAssembler
from src.models.bank_statement import BankStatement
from src.models import Profile, Summary, Transaction, TransactionsMeta
from src.ProfileExtractor import ProfileExtractor
from src.TransactionMapper import TransactionMapper
def main():
   
    pdf_path = r"C:\Users\Komal Patil\Downloads\OpTransactionHistoryTpr30-06-2025.pdf"
    text_extractor = PDFTextExtractor(pdf_path)
    raw_pages = text_extractor.extractor()
   
    print("📄 Extracting tables with pdfplumber...")
    extractor = PlumberTableExtractor(pdf_path)
    tables = extractor.extract_tables()

    profile_extractor = ProfileExtractor(debug=True, preview_lines=20)
    profile_extractor.tables = tables
    profile_list = profile_extractor.extract(raw_pages)
    # print("Profile List: ", profile_list)
    profile_list = ProfileExtractor(debug=False).extract(raw_pages)
    profile_hint = profile_list[0] if profile_list else {}
        
        
    parser = HeaderBasedTableParser()
    transactions = parser.parse(tables)
    print("✅ Tables:", len(tables))
    print("✅ Transactions parsed:", transactions if transactions else "None found")


    normalizer = SchemaNormalizer()
    normalized_txns = normalizer.normalize_transactions(transactions)
    print("✅ Printing Normalized shcema")
    for txn in normalized_txns[:5]:
        print(txn)
  

    summary_data = SummaryExtractor(debug=True).extract(raw_pages, hints={
        "maskedAccNumber": profile_hint.get("maskedAccNumber"),
        "fipId": profile_hint.get("fipId"),
        "fipName": profile_hint.get("fipName"),
    })
    # print("\n✅ Summary:")
    # for k, v in summary_data.items():
    #     print(f"{k}: {v}")

    raw_txns = parser.parse(tables)

# Build a context for stamping common fields
    context = {
        "maskedAccNumber": profile_hint.get("maskedAccNumber") if profile_list else None,
        "fipId": summary_data.get("fipId") or profile_hint.get("fipId"),
        "linkedAccRef": summary_data.get("linkedAccRef"),
        "fnrkAccountId": summary_data.get("fnrkAccountId"),
        "account_type": summary_data.get("account_type") or (profile_hint.get("account_type") if profile_list else None),
    }

    mapper = TransactionMapper(default_account_type="deposit")  # or None
    mapped_txns = mapper.map(raw_txns, context=context)

    print(f"   ➤ Transactions mapped: {len(mapped_txns)}")
    for t in mapped_txns[:5]:
        print("     ", t)

    
    partial_doc = {
        "profile": profile_list,
        "summary": summary_data,
        "transactions": normalized_txns,
        "transactionsMeta": {}  # left empty; assembler computes consolidated meta
    }

    print("\nPartial Doc ")
    print(partial_doc)

    


if __name__ == "__main__":
    main()
