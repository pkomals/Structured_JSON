import os
import sys
import argparse
import json
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

# Add parent directories to path to find src modules
current_dir = Path(__file__).parent
src_dir = current_dir.parent  # up one level to src/
root_dir = src_dir.parent     # up another level to project root
sys.path.insert(0, str(root_dir))

# Import existing extractors
from src.Profile.name_extractor import NameExtractor
from src.Profile.address_extractor import AddressExtractor
from src.Profile.email_extractor import EmailExtractor
from src.Profile.account_no_extractor import AccountNumberExtractor
from src.HeaderParser import HeaderBasedTableParser 
from src.SchemaNormalizer import SchemaNormalizer
from src.Profile.account_type_extractor import AccountTypeExtractor
from src.Profile.nominee_extractor import NomineeExtractor
from src.Profile.type_extractor import TypeExtractor
from src.Summary.summary_extractor import SummaryExtractor

# Import the new Excel extractor
from ExcelExtractor import ExcelExtractor  # Update path as needed

def process_excel(excel_path: str,
                 name_extractor: NameExtractor,
                 addr_extractor: AddressExtractor,
                 first_n_pages: int = 3,
                 password: str = None,
                 output_dir: Path = None,
                 debug: bool = False) -> Dict[str, Any]:
    """
    Extract data from Excel files using existing pipeline
    Returns same structure as PDF pipeline for compatibility
    """
    try:
        print(f"Processing Excel file: {excel_path}")
        
        # 1) Excel extraction (converts to PDF-compatible format)
        excel_extractor = ExcelExtractor(excel_path, password=password)
        raw_pages = excel_extractor.extract_text_pages()[:first_n_pages]
        tables = excel_extractor.extract_tables()
        
        # print(f"Extracted {len(raw_pages)} text pages and {len(tables)} tables")
        print(f"\n=== NAME EXTRACTION DEBUG ===")
        for i, page in enumerate(raw_pages):
            print(f"Excel Text Page {i}:")
            print(f"Text content: '{page['text'][:500]}...'")  # First 500 chars
            print("-" * 50)

        name_res = name_extractor.extract(raw_pages, tables=tables)
        print(f"Name extraction result: {name_res}")
        print("=== END NAME DEBUG ===\n")
        # 2) Run existing extractors (same as PDF pipeline)
        # name_res = name_extractor.extract(raw_pages, tables=tables)
        name_hint = name_res.get("name")
        addr_res = addr_extractor.extract(raw_pages, tables=tables, first_n_pages=2)
        email_res = EmailExtractor().extract(raw_pages, tables=tables, name_hint=name_hint)
        
        # Extract ALL account numbers
        acct_res = AccountNumberExtractor().extract(
            raw_pages, tables=tables, first_n_pages=2,
            skip_promos=True, return_all=True
        )

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

        # 3) Transaction parsing (using existing HeaderBasedTableParser)
        
        parser = HeaderBasedTableParser(debug=True)
        raw_txns = parser.parse(tables)
        # print("=== HEADER MAPPING DEBUG ===")
        # print(f"Parsed raw rows: {len(raw_txns)}")
        # if raw_txns[:1]:
        #     print("Sample raw:", raw_txns[0])

        # 4) Normalization (reuse existing logic)
        profile_account_numbers = [acc.get("account_number") for acc in acct_res] if acct_res else []
        
        normalizer = SchemaNormalizer()
        normalized_txns = normalizer.normalize_transactions(raw_txns, profile_accounts=profile_account_numbers)

        # 5) Filter valid transactions (same logic as PDF)
        valid_transactions = []
        for txn in normalized_txns:
            has_amount = (txn.get('amount') and 
                         str(txn.get('amount')).strip() not in ['', '0', '0.0'])
            
            has_meaningful_narration = (txn.get('narration') and 
                                      len(str(txn.get('narration')).strip()) > 10)
            
            has_date = (txn.get('valueDate') and str(txn.get('valueDate')).strip())
            
            if has_amount or (has_meaningful_narration and has_date):
                valid_transactions.append(txn)
        
        print(f"Valid transactions after filtering: {len(valid_transactions)} (from {len(normalized_txns)} total)")
        
        # 6) Create JSON structure (same as PDF pipeline)
        excel_name = os.path.splitext(os.path.basename(excel_path))[0]
        
        profile = {
            "name": name_res.get("name"),
            "type": type_res.get("type") if type_res else None,
            "email": email_res.get("email"),
            "address": addr_res.get("address"),
            "nominee": nominee_res.get("nominee") if nominee_res else None,
            "account_type": account_type_res.get("account_type") if account_type_res else None,
            "maskedAccNumber": [acc.get("account_number") for acc in acct_res] if acct_res else []      
        }
        
        # Extract summary
        summary_res = SummaryExtractor(debug=debug).extract(
            raw_pages, tables=tables, first_n_pages=3, existing_profile=profile
        )

        # Complete document structure
        document_data = {
            "document_info": {
                "filename": os.path.basename(excel_path),
                "file_type": "excel",
                "processed_at": datetime.now().isoformat(),
                "total_transactions_found": len(normalized_txns),
                "valid_transactions_count": len(valid_transactions)
            },
            "profile": profile,
            "transactions": valid_transactions,
            "summary": summary_res
        }
        
        # 7) Export JSON file
        if output_dir:
            json_filename = f"{excel_name}_analysis.json"
            json_path = output_dir / json_filename
            
            with json_path.open("w", encoding="utf-8") as f:
                json.dump(document_data, f, ensure_ascii=False, indent=2)
            print(f"Exported: {json_path}")
        
        # 8) Return summary
        return {
            "file": os.path.basename(excel_path),
            "file_type": "excel",
            "profile": profile,
            "transaction_count": len(valid_transactions),
            "summary": summary_res,
            "json_exported": str(json_path) if output_dir else None
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "file": os.path.basename(excel_path),
            "error": str(e),
        }


def main():
    ap = argparse.ArgumentParser(
        description="Extract data from Excel files using existing PDF pipeline logic."
    )
    ap.add_argument(
        "-i", "--input_dir", required=True,
        help="Directory containing Excel files"
    )
    ap.add_argument(
        "-o", "--output_dir", default="./output_excel",
        help="Directory to write JSON files (default: ./output_excel)"
    )
    ap.add_argument(
        "-p", "--password", default=None,
        help="Password for encrypted Excel files"
    )
    ap.add_argument(
        "--summary", default="excel_batch_summary.json",
        help="Batch summary JSON filename (default: excel_batch_summary.json)"
    )
    ap.add_argument(
        "--pages", type=int, default=3,
        help="How many sheets to scan per Excel file (default: 3)"
    )
    ap.add_argument(
        "--debug", action="store_true",
        help="Enable debug output"
    )
    args = ap.parse_args()

    input_dir = Path(args.input_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not input_dir.exists() or not input_dir.is_dir():
        print(f"Not a directory: {input_dir}")
        sys.exit(1)

    # Instantiate extractors
    name_extractor = NameExtractor(debug=args.debug)
    addr_extractor = AddressExtractor(debug=args.debug)

    results = []
    excel_files = sorted(p for p in input_dir.iterdir() 
                        if p.suffix.lower() in ['.xlsx', '.xls'])
    
    if not excel_files:
        print("No Excel files found.")
        sys.exit(1)

    print(f"Processing {len(excel_files)} Excel files from: {input_dir}")
    print(f"Output directory: {output_dir}")
    
    for excel_file in excel_files:
        print(f"\nProcessing: {excel_file.name}")
        res = process_excel(
            str(excel_file), 
            name_extractor, 
            addr_extractor, 
            first_n_pages=args.pages,
            password=args.password,
            output_dir=output_dir,
            debug=args.debug
        )
        results.append(res)

    # Print summary (same format as PDF pipeline)
    print("\n" + "="*60)
    print("EXCEL BATCH PROCESSING SUMMARY")
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
                for acc in accounts:
                    print(f"    - {acc}")
            print(f"  Valid Transactions: {r.get('transaction_count', 0)}")
            if r.get('json_exported'):
                print(f"  Exported: {Path(r['json_exported']).name}")

    # Write batch summary
    batch_summary = {
        "processing_info": {
            "processed_at": datetime.now().isoformat(),
            "input_directory": str(input_dir),
            "output_directory": str(output_dir),
            "file_type": "excel",
            "total_files": len(excel_files),
            "successful": success_count,
            "failed": len(excel_files) - success_count
        },
        "total_valid_transactions": total_transactions,
        "results": results
    }
    
    summary_path = output_dir / args.summary
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(batch_summary, f, ensure_ascii=False, indent=2)
    
    print(f"\nBatch summary: {summary_path}")
    print(f"Processed: {success_count}/{len(excel_files)} Excel files")
    print(f"Total valid transactions: {total_transactions}")


if __name__ == "__main__":
    main()