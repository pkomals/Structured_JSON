import os
import sys
import argparse
import json
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

from src.PDFTextExtractor import PDFTextExtractor, PlumberTableExtractor
from src.Profile.name_extractor import NameExtractor
from src.Profile.address_extractor import AddressExtractor
from src.Profile.email_extractor import EmailExtractor
from src.Profile.account_no_extractor import AccountNumberExtractor
from src.HeaderParser import HeaderBasedTableParser 
from src.SchemaNormalizer import SchemaNormalizer
from src.TransactionMapper import TransactionMapper
from src.Profile.account_type_extractor import AccountTypeExtractor
from src.Profile.nominee_extractor import NomineeExtractor
from src.Profile.type_extractor import TypeExtractor
from src.Summary.summary_extractor import SummaryExtractor

def process_pdf(pdf_path: str,
                name_extractor: NameExtractor,
                addr_extractor: AddressExtractor,
                first_n_pages: int = 3,
                output_dir: Path = None,
                debug: bool = False) -> Dict[str, Any]:  # Added debug parameter
    """
    Extract text + tables, then run Name & Address extractors.
    Returns a small dict with per-file results and exports detailed JSON.
    """
    try:
        # 1) raw text (first N pages) + tables
        text_extractor = PDFTextExtractor(pdf_path)
        raw_pages = text_extractor.extractor()[:first_n_pages]

        table_extractor = PlumberTableExtractor(pdf_path)
        tables = table_extractor.extract_tables()

        # 2) run extractors
        name_res = name_extractor.extract(raw_pages, tables=tables)
        name_hint = name_res.get("name")
        addr_res = addr_extractor.extract(raw_pages, tables=tables, first_n_pages=2)
        email_res = EmailExtractor().extract(raw_pages, tables=tables, name_hint=name_hint)
        
        # Extract ALL account numbers
        acct_res = AccountNumberExtractor().extract(
            raw_pages, tables=tables, first_n_pages=2,
            skip_promos=True, return_all=True
        )
        profile_account_numbers = [acc.get("account_number") for acc in acct_res] if acct_res else []

        # Extract other profile fields
        account_type_res = AccountTypeExtractor(debug=debug).extract(  
            raw_pages, tables=tables, first_n_pages=2
        )
        nominee_res = NomineeExtractor(debug=debug).extract(  
            raw_pages, tables=tables, first_n_pages=2, name_hint=name_hint
        )
        type_res = TypeExtractor(debug=debug).extract(  
            raw_pages, tables=tables, first_n_pages=2, name_hint=name_hint
        )

        parser = HeaderBasedTableParser(debug=True)  # Turn off debug for cleaner output
        raw_txns = parser.parse(tables)
        print(f"Parsed raw rows: {len(raw_txns)}")
        if raw_txns[:1]:
            print("Sample raw:", raw_txns[0])

        # print(f"\n=== RAW TRANSACTION DEBUG ===")
        # for i, txn in enumerate(raw_txns[:3]):  # Show first 3
        #     print(f"Raw Transaction {i+1}:")
        #     for field, value in txn.items():
        #         print(f"  {field}: '{value}'")
        #     print("-" * 40)
    
        # print(f"Parsed raw rows: {len(raw_txns)}")
        # if raw_txns[:1]:
        #     print("Sample raw:", raw_txns[0])

        normalizer = SchemaNormalizer()
        normalized_txns = normalizer.normalize_transactions(raw_txns,profile_accounts=profile_account_numbers)

        # 3) Filter valid transactions (more lenient - just need meaningful content)
        valid_transactions = []
        for txn in normalized_txns:
            # A transaction is valid if it has EITHER:
            # - An amount (non-zero, non-empty)
            # - OR a meaningful narration with some date info
            
            has_amount = (txn.get('amount') and 
                         str(txn.get('amount')).strip() not in ['', '0', '0.0'])
            
            has_meaningful_narration = (txn.get('narration') and 
                                      len(str(txn.get('narration')).strip()) > 10)
            
            has_date = (txn.get('valueDate') and str(txn.get('valueDate')).strip())
            
            # Keep transaction if it has amount OR (narration and date)
            if has_amount or (has_meaningful_narration and has_date):
                valid_transactions.append(txn)
        
        print(f"Valid transactions after filtering: {len(valid_transactions)} (from {len(normalized_txns)} total)")
        
        # 4) Create simplified JSON structure (only what you need)
        pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
        
        # Profile data - fixed structure to just store values
        profile = {
            "name": name_res.get("name"),
            "type": type_res.get("type") if type_res else None,
            "email": email_res.get("email"),
            "address": addr_res.get("address"),
            "nominee": nominee_res.get("nominee") if nominee_res else None,
            "account_type": account_type_res.get("account_type") if account_type_res else None,
            "maskedAccNumber": profile_account_numbers      
                }
        
        #Extract summary
        summary_res = SummaryExtractor(debug=debug).extract(
            raw_pages, tables=tables, first_n_pages=3, existing_profile=profile
            )

        # Complete document structure (simplified)
        document_data = {
            "document_info": {
                "filename": os.path.basename(pdf_path),
                "processed_at": datetime.now().isoformat(),
                "total_transactions_found": len(normalized_txns),
                "valid_transactions_count": len(valid_transactions)
            },
            "profile": profile,
            "transactions": valid_transactions,  # Only valid transactions, only SchemaNormalizer fields
            "summary": summary_res
        }
        
        # 5) Export individual JSON file
        if output_dir:
            json_filename = f"{pdf_name}_analysis.json"
            json_path = output_dir / json_filename
            
            with json_path.open("w", encoding="utf-8") as f:
                json.dump(document_data, f, ensure_ascii=False, indent=2)
            print(f"Exported: {json_path}")
        
        # 6) Return summary for batch processing
        return {
            "file": os.path.basename(pdf_path),
            "profile": profile,
            "transaction_count": len(valid_transactions),  # Only valid ones
            "summary": summary_res,
            "json_exported": str(json_path) if output_dir else None
        }
        
    except Exception as e:
        return {
            "file": os.path.basename(pdf_path),
            "error": str(e),
        }


def main():
    ap = argparse.ArgumentParser(
        description="Extract Name + Address + Transactions from all PDFs in a directory."
    )
    ap.add_argument(
        "-i", "--input_dir", required=True,
        help="Directory containing PDFs"
    )
    ap.add_argument(
        "-o", "--output_dir", default="./output",
        help="Directory to write individual JSON files (default: ./output)"
    )
    ap.add_argument(
        "--summary", default="batch_summary.json",
        help="Batch summary JSON filename (default: batch_summary.json)"
    )
    ap.add_argument(
        "--pages", type=int, default=3,
        help="How many initial pages to scan per PDF (default: 3)"
    )
    ap.add_argument(
        "--debug", action="store_true",
        help="Enable extractor debug prints"
    )
    args = ap.parse_args()

    input_dir = Path(args.input_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not input_dir.exists() or not input_dir.is_dir():
        print(f"Not a directory: {input_dir}")
        sys.exit(1)

    # Instantiate extractors (debug flag passes through)
    name_extractor = NameExtractor(debug=args.debug)
    addr_extractor = AddressExtractor(debug=args.debug)

    results = []
    pdfs = sorted(p for p in input_dir.iterdir() if p.suffix.lower() == ".pdf")
    if not pdfs:
        print("No PDFs found.")
        sys.exit(1)

    print(f"Processing {len(pdfs)} PDFs from: {input_dir}")
    print(f"Output directory: {output_dir}")
    
    for pdf in pdfs:
        print(f"\nProcessing: {pdf.name}")
        res = process_pdf(
            str(pdf), 
            name_extractor, 
            addr_extractor, 
            first_n_pages=args.pages,
            output_dir=output_dir,
            debug=args.debug  # Pass debug parameter
        )
        results.append(res)

    # Pretty print summary
    print("\n" + "="*60)
    print("BATCH PROCESSING SUMMARY")
    print("="*60)
    
    total_transactions = 0
    success_count = 0
    
    for r in results:
        if "error" in r:
            print(f"ERROR {r['file']}: {r['error']}")
        else:
            success_count += 1
            total_transactions += r.get('transaction_count', 0)
            
            profile = r.get('profile', {})
            name = profile.get('name', 'N/A')
            account_type = profile.get('account_type', 'N/A')
            holder_type = profile.get('type', 'N/A')
            nominee = profile.get('nominee', 'N/A')
            accounts = profile.get('maskedAccNumber', [])
            
            print(f"SUCCESS {r['file']}:")
            print(f"  Name: {name}")
            print(f"  Account Type: {account_type}")
            print(f"  Type: {holder_type}")
            print(f"  Nominee: {nominee}")
            print(f"  Accounts: {len(accounts)} found")
            if accounts:
                for acc in accounts:  # Show ALL accounts
                    print(f"    - {acc}")
            print(f"  Valid Transactions: {r.get('transaction_count', 0)}")
            if r.get('json_exported'):
                print(f"  Exported: {Path(r['json_exported']).name}")

    # Write batch summary JSON (simplified)
    batch_summary = {
        "processing_info": {
            "processed_at": datetime.now().isoformat(),
            "input_directory": str(input_dir),
            "output_directory": str(output_dir),
            "total_pdfs": len(pdfs),
            "successful": success_count,
            "failed": len(pdfs) - success_count
        },
        "total_valid_transactions": total_transactions,
        "results": results
    }
    
    summary_path = output_dir / args.summary
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(batch_summary, f, ensure_ascii=False, indent=2)
    
    print(f"\nBatch summary: {summary_path}")
    print(f"Processed: {success_count}/{len(pdfs)} PDFs")
    print(f"Total valid transactions: {total_transactions}")


if __name__ == "__main__":
    main()