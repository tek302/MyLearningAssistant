"""Smoke test for canonical SQL migration coverage (P0-1)."""

from pathlib import Path


def test_p0_1_schema_migration_coverage():
    root = Path(__file__).resolve().parents[1]
    sql_dir = root / "sql"
    readme = sql_dir / "README.md"

    required_files = [
        "00_enable_extensions.sql",
        "10_schema_core.sql",
        "50_schema_jobs.sql",
        "51_jobs_payload.sql",
        "52_schema_recommendations.sql",
        "53_schema_alpha_feedback_memory.sql",
    ]

    missing_files = [f for f in required_files if not (sql_dir / f).exists()]
    assert not missing_files, f"Missing sql files: {missing_files}"

    combined = "\n".join((sql_dir / f).read_text(encoding="utf-8") for f in required_files).lower()

    required_tables = [
        "users",
        "sources",
        "chunks",
        "embeddings",
        "summaries",
        "jobs",
        "recommendations",
        "notes",
        "feedback_events",
        "user_keywords",
        "keyword_suggestions",
        "recommendation_generation_runs",
        "user_interest_profiles",
    ]

    missing_tables = []
    for t in required_tables:
        token = f"create table if not exists public.{t}"
        token_alt = f"create table if not exists {t}"
        if token not in combined and token_alt not in combined:
            missing_tables.append(t)
    assert not missing_tables, f"Missing create-table definitions: {missing_tables}"

    required_markers = [
        "uq_user_keywords_user_keyword_active",
        "uq_feedback_events_client_event_id",
        "idx_recommendation_runs_user_week_created",
    ]
    missing_markers = [m for m in required_markers if m not in combined]
    assert not missing_markers, f"Missing required index/constraint markers: {missing_markers}"

    readme_text = readme.read_text(encoding="utf-8")
    assert "53_schema_alpha_feedback_memory.sql" in readme_text, (
        "README does not include 53_schema_alpha_feedback_memory.sql"
    )

