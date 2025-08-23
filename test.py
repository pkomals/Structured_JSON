# # main_profile_fields.py
# import os
# import sys
# import argparse
# import json
# from pathlib import Path
# from typing import Dict, Any

# from src.PDFTextExtractor import PDFTextExtractor, PlumberTableExtractor
# from src.Profile.name_extractor import NameExtractor
# from src.Profile.address_extractor import AddressExtractor
# from src.Profile.email_extractor import EmailExtractor
# from src.Profile.account_no_extractor import AccountNumberExtractor
# from src.Transactions.transaction_extractor import TransactionExtractor
# from src.HeaderParser import HeaderBasedTableParser 
# from src.SchemaNormalizer import SchemaNormalizer
# from src.TransactionMapper import TransactionMapper

# def process_pdf(pdf_path: str,
#                 name_extractor: NameExtractor,
#                 addr_extractor: AddressExtractor,
#                 first_n_pages: int = 3) -> Dict[str, Any]:
#     """
#     Extract text + tables, then run Name & Address extractors.
#     Returns a small dict with per-file results.
#     """
#     try:
#         # 1) raw text (first N pages) + tables
#         text_extractor = PDFTextExtractor(pdf_path)
#         raw_pages = text_extractor.extractor()[:first_n_pages]

#         table_extractor = PlumberTableExtractor(pdf_path)
#         tables = table_extractor.extract_tables()

#         # 2) run extractors
#         name_res = name_extractor.extract(raw_pages, tables=tables)
#         name_hint = name_res.get("name")
#         addr_res = addr_extractor.extract(raw_pages, tables=tables, first_n_pages=2)
#         email_res = EmailExtractor().extract(raw_pages, tables=tables, name_hint=name_hint)
#         # acct_res = AccountNumberExtractor().extract(raw_pages, tables=tables, first_n_pages=2, skip_promos=True,return_all=True)
#          # 🔹 get ALL account numbers
#         acct_res = AccountNumberExtractor().extract(
#             raw_pages, tables=tables, first_n_pages=2,
#             skip_promos=True, return_all=True
#         )
#         # Add context after summary
#         context = {
#             # "fipId": summary_data.get("fipId") or profile_hint.get("fipId"),
#             # "maskedAccNumber": profile_hint.get("maskedAccNumber") or primary_account_number,
#             # "account_type": summary_data.get("account_type") or profile_hint.get("account_type"),
#         } or None
        
#         parser = HeaderBasedTableParser(debug=True)
#         raw_txns = parser.parse(tables)

#         # print(f"Parsed raw rows: {len(raw_txns)}")
#         # if raw_txns[:1]:
#         #     print("Sample raw:", raw_txns[0])

#         normalizer = SchemaNormalizer()
#         grouped_norm = normalizer.normalize_grouped(raw_txns)
#         # print(f"Normalized rows: {len(normalized_txns)}")
#         # for t in normalized_txns[:5]:
#         #     print(t)

#         # 3) Extract transactions

#         # Example: print summary
#         total = sum(len(v) for v in grouped_norm.values())
#         print(f"Parsed transactions (grouped): {total} rows across {len(grouped_norm)} page(s)")
#         for page in sorted(grouped_norm):
#             print(f"\n— Page {page} — ({len(grouped_norm[page])} rows)")
#             for t in grouped_norm[page][:5]:   # preview first 5 per page
#                 print("  ", t)

#         # If you want to save per-file JSON with grouping:
#         result = {
#             "file": os.path.basename(pdf_path),
#             "transactions_by_page": grouped_norm
#     }

#         # tx_extractor = TransactionExtractor()
#         # transactions = tx_extractor.extract(
#         #     normalized_txns,
#         #     context={"maskedAccNumber": primary_account_number}
#         # )

#         # print(f"Parsed {len(transactions)} transactions")
#         # for t in transactions[:5]:
#         #     print(t)

      
#         return {
#             "file": os.path.basename(pdf_path),
#             "name": {
#                 "value": name_res.get("name"),
#                 "confidence": name_res.get("confidence"),
#                 "evidence": name_res.get("evidence"),
#             },
#             "address": {
#                 "value": addr_res.get("address"),
#                 "confidence": addr_res.get("confidence"),
#                 "evidence": addr_res.get("evidence"),
#             },
#             "email": {
#                 "value": email_res.get("email"),
#                 "confidence": email_res.get("confidence"),
#                 "evidence": email_res.get("evidence"),
#             },
#             "accounts": acct_res
#         }
#     except Exception as e:
#         return {
#             "file": os.path.basename(pdf_path),
#             "error": str(e),
#         }


# def main():
#     ap = argparse.ArgumentParser(
#         description="Extract Name + Address from all PDFs in a directory."
#     )
#     ap.add_argument(
#         "-i", "--input_dir", required=True,
#         help="Directory containing PDFs"
#     )
#     ap.add_argument(
#         "-o", "--out", default="name_address_results.json",
#         help="Where to write the combined JSON output"
#     )
#     ap.add_argument(
#         "--pages", type=int, default=3,
#         help="How many initial pages to scan per PDF (default: 3)"
#     )
#     ap.add_argument(
#         "--debug", action="store_true",
#         help="Enable extractor debug prints"
#     )
#     args = ap.parse_args()

#     input_dir = Path(args.input_dir).expanduser().resolve()
#     if not input_dir.exists() or not input_dir.is_dir():
#         print(f"❌ Not a directory: {input_dir}")
#         sys.exit(1)

#     # Instantiate extractors (debug flag passes through)
#     name_extractor = NameExtractor(debug=args.debug)
#     addr_extractor = AddressExtractor(debug=args.debug)

#     results = []
#     pdfs = sorted(p for p in input_dir.iterdir() if p.suffix.lower() == ".pdf")
#     if not pdfs:
#         print("❌ No PDFs found.")
#         sys.exit(1)

#     print(f"🔎 Scanning {len(pdfs)} PDFs in: {input_dir}")
#     for pdf in pdfs:
#         print(f"• {pdf.name}")
#         res = process_pdf(str(pdf), name_extractor, addr_extractor, first_n_pages=args.pages)
#         results.append(res)

#     # Pretty print summary
#     print("\n=== Results ===")
#     for r in results:
#         if "error" in r:
#             print(f"{r['file']}: ERROR -> {r['error']}")
#         else:
#             n = r["name"]["value"]
#             a = r["address"]["value"]
#             e = r["email"]["value"]
            
#             # acc=r["account"]["value"]
#             print(f"{r['file']}:")
#             # print(f"   Name   : {n}  (conf {r['name']['confidence']}, via {r['name']['evidence']})")
#             # print(f"   Address: {a}  (conf {r['address']['confidence']}, via {r['address']['evidence']})")
#             # print(f"   Email  : {e}  (conf {r['email']['confidence']}, via {r['email']['evidence']})")
            
#             # 🔹 Print all account numbers
#             accounts = r.get("accounts", [])
#             if accounts:
#                 print("   Accounts:")
#                 for acc in accounts:
#                     print(f"{acc['account_number']}  (conf {acc['confidence']}, via {acc['evidence']})")
#             else:
#                  print("Accounts: None found")


            

#     # Write JSON
#     out_path = Path(args.out).expanduser().resolve()
#     with out_path.open("w", encoding="utf-8") as f:
#         json.dump(results, f, ensure_ascii=False, indent=2)
#     print(f"\n✅ Wrote: {out_path}")

    


# if __name__ == "__main__":
#     main()


# main_profile_fields.py
import os
import sys
import argparse
import json
from pathlib import Path
from typing import Dict, Any

from src.PDFTextExtractor import PDFTextExtractor, PlumberTableExtractor
from src.Profile.name_extractor import NameExtractor
from src.Profile.address_extractor import AddressExtractor
from src.Profile.email_extractor import EmailExtractor
from src.Profile.account_no_extractor import AccountNumberExtractor
from src.Transactions.transaction_extractor import TransactionExtractor
from src.HeaderParser import HeaderBasedTableParser 
from src.SchemaNormalizer import SchemaNormalizer
from src.TransactionMapper import TransactionMapper

def process_pdf(pdf_path: str,
                name_extractor: NameExtractor,
                addr_extractor: AddressExtractor,
                first_n_pages: int = 3,
                include_transactions: bool = False) -> Dict[str, Any]:
    """
    Extract text + tables, then run Name & Address extractors.
    Returns a small dict with per-file results.
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
        
        # get ALL account numbers
        acct_res = AccountNumberExtractor().extract(
            raw_pages, tables=tables, first_n_pages=2,
            skip_promos=True, return_all=True
        )
        
        # Primary account number for context
        primary_account_number = ""
        if acct_res and len(acct_res) > 0:
            primary_account_number = acct_res[0].get("account_number", "")

        result = {
            "file": os.path.basename(pdf_path),
            "name": {
                "value": name_res.get("name"),
                "confidence": name_res.get("confidence"),
                "evidence": name_res.get("evidence"),
            },
            "address": {
                "value": addr_res.get("address"),
                "confidence": addr_res.get("confidence"),
                "evidence": addr_res.get("evidence"),
            },
            "email": {
                "value": email_res.get("email"),
                "confidence": email_res.get("confidence"),
                "evidence": email_res.get("evidence"),
            },
            "accounts": acct_res
        }

        # 3) Extract transactions if requested
        if include_transactions:
            parser = HeaderBasedTableParser(debug=True)
            raw_txns = parser.parse(tables)

            normalizer = SchemaNormalizer()
            grouped_norm = normalizer.normalize_grouped(raw_txns)
            
            # Flatten grouped transactions for JSON output
            all_transactions = []
            for page, txns in grouped_norm.items():
                for txn in txns:
                    txn["page"] = page  # Add page info to each transaction
                    all_transactions.append(txn)

            # Post-process transactions with context
            context = {
                "maskedAccNumber": primary_account_number
            }
            
            tx_extractor = TransactionExtractor()
            final_transactions = tx_extractor.extract(
                all_transactions,
                context=context
            )

            # Add transaction data to result
            result["transactions"] = final_transactions
            result["transaction_summary"] = {
                "total_count": len(final_transactions),
                "pages_processed": len(grouped_norm),
                "raw_count": len(all_transactions)
            }

            # Print summary
            total = sum(len(v) for v in grouped_norm.values())
            print(f"Parsed transactions (grouped): {total} rows across {len(grouped_norm)} page(s)")
            print(f"Final processed transactions: {len(final_transactions)}")

        return result

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
        "-o", "--out", default="results.json",
        help="Where to write the combined JSON output"
    )
    ap.add_argument(
        "--pages", type=int, default=3,
        help="How many initial pages to scan per PDF (default: 3)"
    )
    ap.add_argument(
        "--debug", action="store_true",
        help="Enable extractor debug prints"
    )
    ap.add_argument(
        "--include-transactions", action="store_true",
        help="Include transaction data in the output JSON"
    )
    ap.add_argument(
        "--transactions-only", action="store_true", 
        help="Output only transaction data (exclude profile fields)"
    )
    ap.add_argument(
        "--transactions-file", 
        help="Separate JSON file for transactions only (optional)"
    )
    args = ap.parse_args()

    input_dir = Path(args.input_dir).expanduser().resolve()
    if not input_dir.exists() or not input_dir.is_dir():
        print(f"Not a directory: {input_dir}")
        sys.exit(1)

    # Instantiate extractors (debug flag passes through)
    name_extractor = NameExtractor(debug=args.debug)
    addr_extractor = AddressExtractor(debug=args.debug)

    results = []
    transaction_results = []
    pdfs = sorted(p for p in input_dir.iterdir() if p.suffix.lower() == ".pdf")
    if not pdfs:
        print("No PDFs found.")
        sys.exit(1)

    print(f"Scanning {len(pdfs)} PDFs in: {input_dir}")
    for pdf in pdfs:
        print(f"• {pdf.name}")
        include_txns = args.include_transactions or args.transactions_only
        res = process_pdf(str(pdf), name_extractor, addr_extractor, 
                         first_n_pages=args.pages, include_transactions=include_txns)
        results.append(res)

        # Collect transactions separately if needed
        if include_txns and "transactions" in res:
            transaction_results.append({
                "file": res["file"],
                "transactions": res["transactions"],
                "transaction_summary": res.get("transaction_summary")
            })

    # Pretty print summary
    print("\n=== Results ===")
    for r in results:
        if "error" in r:
            print(f"{r['file']}: ERROR -> {r['error']}")
        else:
            print(f"{r['file']}:")
            
            if not args.transactions_only:
                # Print profile data
                n = r["name"]["value"]
                a = r["address"]["value"]
                e = r["email"]["value"]
                print(f"   Name   : {n}  (conf {r['name']['confidence']}, via {r['name']['evidence']})")
                print(f"   Address: {a}  (conf {r['address']['confidence']}, via {r['address']['evidence']})")
                print(f"   Email  : {e}  (conf {r['email']['confidence']}, via {r['email']['evidence']})")
                
                accounts = r.get("accounts", [])
                if accounts:
                    print("   Accounts:")
                    for acc in accounts:
                        print(f"     {acc['account_number']}  (conf {acc['confidence']}, via {acc['evidence']})")
                else:
                    print("   Accounts: None found")
            
            # Print transaction summary
            if "transactions" in r:
                summary = r.get("transaction_summary", {})
                print(f"   Transactions: {summary.get('total_count', 0)} processed from {summary.get('raw_count', 0)} raw transactions across {summary.get('pages_processed', 0)} pages")

    # Prepare output based on flags
    if args.transactions_only:
        # Only include transaction data
        output_data = transaction_results
    elif not args.include_transactions:
        # Remove transaction data to keep JSON smaller
        output_data = []
        for r in results:
            clean_result = {k: v for k, v in r.items() if k not in ["transactions", "transaction_summary"]}
            output_data.append(clean_result)
    else:
        # Include everything
        output_data = results

    # Write main JSON
    out_path = Path(args.out).expanduser().resolve()
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"\nWrote main results: {out_path}")

    # Write separate transactions file if specified
    if args.transactions_file and transaction_results:
        txn_path = Path(args.transactions_file).expanduser().resolve()
        with txn_path.open("w", encoding="utf-8") as f:
            json.dump(transaction_results, f, ensure_ascii=False, indent=2)
        print(f"Wrote transactions file: {txn_path}")

    print(f"\nProcessed {len(results)} files successfully")


if __name__ == "__main__":
    main()