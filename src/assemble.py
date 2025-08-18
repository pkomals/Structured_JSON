# src/assemble.py
import json
from pathlib import Path
from bank_statement import BankStatement, Profile, Summary, Transaction, TransactionMeta

def assemble_bank_statement(
    profile_data,
    summary_data,
    transactions_data,
    transactions_meta_data,
    output_path
):
    # Create the BankStatement object
    bank_statement = BankStatement(
        profile=[Profile(**p) for p in profile_data],
        summary=Summary(**summary_data),
        transactions=[Transaction(**t) for t in transactions_data],
        transactionsMeta=TransactionMeta(**transactions_meta_data)
    )

    # Serialize to JSON
    json_output = bank_statement.model_dump()

    # Save to file
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(json_output, f, ensure_ascii=False, indent=2)

    print(f"✅ Saved bank statement to {output_path}")
    return bank_statement

if __name__ == "__main__":
    #