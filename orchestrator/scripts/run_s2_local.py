"""
Run S2 consolidation locally without starting the server or using Android login.
Uses DB + OpenAI only. Load .env from orchestrator root (run from orchestrator: python scripts/run_s2_local.py).
"""
import os
import sys

# Ensure app is importable when run as scripts/run_s2_local.py from orchestrator
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import load_env

load_env()

from app.db.repo import SupabaseRepo
from app.services.s2_consolidation import run_s2_consolidation


def main():
    repo = SupabaseRepo()
    user_ids = repo.get_user_ids_with_sources_since(days=7)
    if not user_ids:
        print("No users with sources in the last 7 days. Add sources and S1 summaries first.")
        return
    user_id = user_ids[0]
    print(f"Running S2 consolidation for user_id={user_id} ...")
    ok, reason = run_s2_consolidation(user_id, week_start=None, days=7)
    if ok:
        print("Done. S2 created.")
    else:
        print(f"Done. S2 not created: {reason or 'unknown'}")


if __name__ == "__main__":
    main()
