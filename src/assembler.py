# src/assembler.py
from __future__ import annotations

from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path
from copy import deepcopy
import json

from src.Schema.bank_statement import (
    BankStatement, Profile, Summary, Transaction, TransactionsMeta
)
from typing import Any, Dict, Iterable, List, Optional

def _is_int(v: Any) -> bool:
    try:
        int(v)
        return True
    except Exception:
        return False

def _to_int_or_none(v: Any) -> Optional[int]:
    if v is None: 
        return None
    if isinstance(v, (int,)):
        return v
    s = str(v).strip()
    if not s: 
        return None
    try:
        return int(s)
    except Exception:
        try:
            return int(float(s.replace(",", "")))
        except Exception:
            return None

def _pick_first_non_null(*vals):
    for v in vals:
        if v not in (None, "", []):
            return v
    return None

def _txn_time(txn: Dict[str, Any]) -> Optional[int]:
    """Prefer transactionTimestamp, else valueDate."""
    return _to_int_or_none(txn.get("transactionTimestamp")) or _to_int_or_none(txn.get("valueDate"))


# ---------------------------
# Helpers
# ---------------------------

def _epoch_ms_or_none(x) -> Optional[int]:
    if x is None:
        return None
    try:
        return int(x)
    except Exception:
        return None

def _coalesce_non_empty(*vals):
    for v in vals:
        if v not in (None, "", "null", "NULL"):
            return v
    return None

def _key_account(summary: Dict[str, Any]) -> Tuple[str, str, str]:
    """
    Group by these 3 fields to identify an account:
      (fipId, maskedAccNumber, linkedAccRef)
    Adjust if your data uses a different stable key.
    """
    return (
        (summary.get("fipId") or "").strip().upper(),
        (summary.get("maskedAccNumber") or "").strip().upper(),
        (summary.get("linkedAccRef") or "").strip().upper(),
    )

def _key_profile(p: Dict[str, Any]) -> Tuple[str, str, str]:
    """
    Dedupe profiles within an account by (PAN, maskedAccNumber, fipId).
    """
    return (
        (p.get("pan") or "").strip().upper(),
        (p.get("maskedAccNumber") or "").strip().upper(),
        (p.get("fipId") or "").strip().upper(),
    )

def _latest_by_ts(a: Dict[str, Any], b: Dict[str, Any], ts_key: str) -> Dict[str, Any]:
    ta = _epoch_ms_or_none(a.get(ts_key))
    tb = _epoch_ms_or_none(b.get(ts_key))
    if ta is None and tb is None:
        return a
    if ta is None:
        return b
    if tb is None:
        return a
    return a if ta >= tb else b

def _merge_numeric_str(old, new):
    """
    For numeric-like fields allowed as str/number.
    Prefer non-empty 'new'; if both present, keep 'new' (latest).
    """
    if new not in (None, ""):
        return new
    return old

def _safe_name_component(s: Optional[str]) -> str:
    if not s:
        return "unknown"
    return "".join(ch for ch in s if ch.isalnum() or ch in ("-", "_")).strip() or "unknown"


# ---------------------------
# Core assembler
# ---------------------------

class BankStatementAssembler:
    """
    Collect many single-statement partials, group by account, merge,
    and write one JSON per account.
    """

    def __init__(self):
        self.partials: List[Dict[str, Any]] = []

    def add_partial(self, partial: Dict[str, Any]) -> None:
        """Add one parsed statement (profile/summary/transactions/meta)."""
        if not isinstance(partial, dict):
            raise TypeError("partial must be a dict shaped like a single statement output.")
        self.partials.append(partial)

    # -------- grouping --------
    def _group_partials_by_account(self) -> Dict[Tuple[str, str, str], List[Dict[str, Any]]]:
        groups: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
        for p in self.partials:
            summary = p.get("summary", {}) or {}
            key = _key_account(summary)
            groups.setdefault(key, []).append(p)
        return groups

    # -------- merging within an account --------
    def _merge_profiles(self, profile_lists: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        merged: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        for prof_list in profile_lists:
            for p in prof_list or []:
                key = _key_profile(p)
                if key not in merged:
                    merged[key] = deepcopy(p)
                    continue
                base = merged[key]
                for k, v in p.items():
                    if base.get(k) in (None, "") and v not in (None, ""):
                        base[k] = v
                # ckyc: prefer True if seen anywhere
                if p.get("ckycCompliance") is True:
                    base["ckycCompliance"] = True
        return list(merged.values())

    def _merge_summaries(self, summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Merge multiple summaries for the SAME account (same fipId/maskedAccNumber/linkedAccRef).
        Prefer the one with the latest balanceDateTime, then coalesce fields.
        """
        if not summaries:
            return Summary().model_dump()

        # Start with the latest by balanceDateTime
        latest = summaries[0]
        for s in summaries[1:]:
            latest = _latest_by_ts(latest, s, "balanceDateTime")

        merged = deepcopy(latest)
        for s in summaries:
            for k, v in s.items():
                if merged.get(k) in (None, "") and v not in (None, ""):
                    merged[k] = v
                if k in ("currentBalance", "currentODLimit", "drawingLimit", "pending_amount"):
                    merged[k] = _merge_numeric_str(merged.get(k), v)

        return Summary(**merged).model_dump()

    def _merge_transactions(self, txn_lists: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        combined: List[Dict[str, Any]] = []
        for lst in txn_lists:
            if lst:
                combined.extend(lst)

        # Optional: dedupe by (txnId, transactionTimestamp, amount, maskedAccNumber)
        seen = set()
        unique: List[Dict[str, Any]] = []
        for t in combined:
            key = (
                (t.get("txnId") or "").strip().upper(),
                str(t.get("transactionTimestamp") or ""),
                str(t.get("amount") or ""),
                (t.get("maskedAccNumber") or "").strip().upper(),
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(t)

        unique.sort(key=lambda x: _epoch_ms_or_none(x.get("transactionTimestamp")) or -1)
        return [Transaction(**t).model_dump() for t in unique]

    def _compute_transactions_meta(
        self,
        summaries: List[Dict[str, Any]],
        transactions: List[Dict[str, Any]],
        profiles: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Compute transactionsMeta for one merged account bundle.
        Inputs are already scoped to a single account (post-grouping).
        """
        # Sources to pick identity fields (priority: summary → profile → txn context)
        sum0 = summaries[0] if summaries else {}
        prof0 = profiles[0] if profiles else {}

        fipId = _pick_first_non_null(
            sum0.get("fipId"),
            prof0.get("fipId"),
            # any txn may carry it
            next((t.get("fipId") for t in transactions if t.get("fipId")), None),
        )

        linkedAccRef = _pick_first_non_null(
            sum0.get("linkedAccRef"),
            prof0.get("linkedAccRef"),
            next((t.get("linkedAccRef") for t in transactions if t.get("linkedAccRef")), None),
        )

        fnrkAccountId = _pick_first_non_null(
            sum0.get("fnrkAccountId"),
            prof0.get("fnrkAccountId"),
            next((t.get("fnrkAccountId") for t in transactions if t.get("fnrkAccountId")), None),
        )

        maskedAccNumber = _pick_first_non_null(
            sum0.get("maskedAccNumber"),
            prof0.get("maskedAccNumber"),
            next((t.get("maskedAccNumber") for t in transactions if t.get("maskedAccNumber")), None),
        )

        # Time bounds from transactions
        times = [t for t in (_txn_time(tx) for tx in transactions) if t is not None]
        from_ts = min(times) if times else None
        to_ts = max(times) if times else None

        # No transactions? Try to fall back to summary balance timestamp for both.
        if from_ts is None and to_ts is None and summaries:
            bal_ts = _to_int_or_none(sum0.get("balanceDateTime"))
            from_ts = bal_ts
            to_ts = bal_ts

        meta = {
            "fipId": fipId,
            "toTimestamp": to_ts,
            "linkedAccRef": linkedAccRef,
            "fnrkAccountId": fnrkAccountId,
            "fromTimestamp": from_ts,
            "maskedAccNumber": maskedAccNumber,
            "noOfTransactions": len(transactions) if transactions else 0,
        }
        return meta

    # -------- public: assemble per account --------
    def assemble_per_account(self, output_dir: str) -> List[Dict[str, Any]]:
        """
        Groups all added partials by account and writes one JSON per group.
        Returns the list of dicts (one per account).
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        groups = self._group_partials_by_account()
        results: List[Dict[str, Any]] = []

        for key, items in groups.items():
            # Collect components
            profile_lists = [i.get("profile", []) for i in items]
            summaries     = [i.get("summary", {}) for i in items]
            txns_lists    = [i.get("transactions", []) for i in items]

            merged_profiles = self._merge_profiles(profile_lists)
            merged_summary  = self._merge_summaries(summaries)
            merged_txns     = self._merge_transactions(txns_lists)
            merged_meta     = self._compute_transactions_meta(summaries=[merged_summary] if merged_summary else [],
                    transactions=merged_txns or [],
                    profiles=merged_profiles or [],)

            final_doc = {
        "profile": merged_profiles or [],
        "summary": merged_summary or {},
        "transactions": merged_txns or [],
        "transactionsMeta":merged_meta,
}

            # # Build final validated doc
            # doc = BankStatement(
            #     profile=[Profile(**p) for p in merged_profiles],
            #     summary=Summary(**merged_summary),
            #     transactions=[Transaction(**t) for t in merged_txns],
            #     transactionsMeta=TransactionsMeta(**merged_meta),
            # ).model_dump()

            # Filename per account
            fip, masked, linked = key
            fname = f"bank_{_safe_name_component(fip)}_{_safe_name_component(masked)}_{_safe_name_component(linked)}.json"
            out_path = Path(output_dir) / fname

            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(final_doc, f, ensure_ascii=False, indent=2)

            results.append(final_doc)

        return results
