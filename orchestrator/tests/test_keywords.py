"""
Test 2-Stage Pipeline: keyword CRUD, suggestions accept/reject, weight recalc, history.
Uses AUTH_BYPASS_USER_ID=dev-user via conftest.
"""
import os
import uuid
import pytest
import psycopg
from fastapi.testclient import TestClient
from dotenv import load_dotenv

load_dotenv()
os.environ["AUTH_BYPASS_USER_ID"] = "dev-user"

from app.main import app  # noqa: E402

client = TestClient(app)
TEST_USER = "dev-user"
_cleanup_keyword_ids: list[str] = []
_cleanup_suggestion_ids: list[str] = []


def _db_url() -> str:
    url = os.getenv("SUPABASE_DB_URL")
    if not url:
        pytest.skip("SUPABASE_DB_URL not set")
    return url


@pytest.fixture(autouse=True, scope="module")
def cleanup_after_all():
    """Delete all test keywords/suggestions after module finishes."""
    yield
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        return
    from app.db.repo import SupabaseRepo
    repo = SupabaseRepo()
    user_uuid = repo._get_or_create_user_id(TEST_USER)
    conn = psycopg.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM keyword_suggestions WHERE user_id = %s", (user_uuid,))
            cur.execute("DELETE FROM user_keywords WHERE user_id = %s", (user_uuid,))
            cur.execute("DELETE FROM recommendation_generation_runs WHERE user_id = %s", (user_uuid,))
            conn.commit()
    finally:
        conn.close()


# ─── 1. Keyword CRUD ───


class TestKeywordCRUD:
    def test_list_empty(self):
        r = client.get("/keywords")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "total_active" in data

    def test_create_keyword(self):
        r = client.post("/keywords", json={"keyword": "agent memory"})
        assert r.status_code == 201
        data = r.json()
        assert data["keyword"] == "agent memory"
        assert data["status"] == "active"
        _cleanup_keyword_ids.append(data["id"])

    def test_create_second_keyword(self):
        r = client.post("/keywords", json={"keyword": "graph RAG"})
        assert r.status_code == 201
        _cleanup_keyword_ids.append(r.json()["id"])

    def test_create_third_keyword(self):
        r = client.post("/keywords", json={"keyword": "retrieval augmented generation"})
        assert r.status_code == 201
        _cleanup_keyword_ids.append(r.json()["id"])

    def test_duplicate_keyword_409(self):
        r = client.post("/keywords", json={"keyword": "agent memory"})
        assert r.status_code == 409

    def test_list_after_create(self):
        r = client.get("/keywords")
        assert r.status_code == 200
        data = r.json()
        assert data["total_active"] >= 3
        kws = [item["keyword"] for item in data["items"]]
        assert "agent memory" in kws
        assert "graph RAG" in kws

    def test_list_filter_by_status(self):
        r = client.get("/keywords?status=active")
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item["status"] == "active"

    def test_update_keyword_status(self):
        kw_id = _cleanup_keyword_ids[0]
        r = client.patch(f"/keywords/{kw_id}", json={"status": "declining"})
        assert r.status_code == 200
        assert r.json()["updated"] is True

        r2 = client.get("/keywords?status=declining")
        ids = [item["id"] for item in r2.json()["items"]]
        assert kw_id in ids

        client.patch(f"/keywords/{kw_id}", json={"status": "active"})

    def test_delete_keyword_archives(self):
        r = client.post("/keywords", json={"keyword": "to_be_deleted"})
        assert r.status_code == 201
        kw_id = r.json()["id"]

        r2 = client.delete(f"/keywords/{kw_id}")
        assert r2.status_code == 204

        r3 = client.get("/keywords?status=active")
        ids = [item["id"] for item in r3.json()["items"]]
        assert kw_id not in ids

    def test_delete_nonexistent_404(self):
        r = client.delete(f"/keywords/{uuid.uuid4()}")
        assert r.status_code == 404


# ─── 2. Keyword Suggestions ───


class TestKeywordSuggestions:
    """Test Stage 1 suggestion endpoints using direct DB insertion (no LLM)."""

    _shared_suggestion_ids: list[str] = []

    @classmethod
    def _ensure_suggestions(cls):
        if cls._shared_suggestion_ids:
            return
        from app.db.repo import SupabaseRepo
        repo = SupabaseRepo()
        suggestions = [
            {"keyword": f"multi-agent systems {uuid.uuid4().hex[:6]}", "parent_keyword": "agent memory", "type": "derivative", "reason": "test", "confidence": 0.8},
            {"keyword": f"neuro-symbolic AI {uuid.uuid4().hex[:6]}", "parent_keyword": None, "type": "emerging", "reason": "test", "confidence": 0.7},
        ]
        ids = repo.insert_keyword_suggestions(TEST_USER, suggestions, "2026-03-09")
        _cleanup_suggestion_ids.extend(ids)
        cls._shared_suggestion_ids = ids

    def test_01_list_suggestions(self):
        self._ensure_suggestions()
        r = client.get("/keywords/suggestions")
        assert r.status_code == 200
        data = r.json()
        assert len(data["items"]) >= 2

    def test_02_list_suggestions_filter_week(self):
        self._ensure_suggestions()
        r = client.get("/keywords/suggestions?week_start=2026-03-09")
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item["week_start"] == "2026-03-09"

    def test_03_accept_suggestion_creates_keyword(self):
        self._ensure_suggestions()
        sid = self._shared_suggestion_ids[0]
        r = client.post(f"/keywords/suggestions/{sid}/accept")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "accepted"
        assert data["created_keyword_id"] is not None

    def test_04_accept_already_responded_404(self):
        self._ensure_suggestions()
        sid = self._shared_suggestion_ids[0]
        r = client.post(f"/keywords/suggestions/{sid}/accept")
        assert r.status_code == 404

    def test_05_reject_suggestion(self):
        self._ensure_suggestions()
        sid = self._shared_suggestion_ids[1]
        r = client.post(f"/keywords/suggestions/{sid}/reject")
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"

    def test_06_reject_nonexistent_404(self):
        r = client.post(f"/keywords/suggestions/{uuid.uuid4()}/reject")
        assert r.status_code == 404


# ─── 3. Keyword History ───


class TestKeywordHistory:
    def test_history_returns_events(self):
        r = client.get("/keywords/history")
        assert r.status_code == 200
        data = r.json()
        assert "events" in data
        if data["events"]:
            assert "type" in data["events"][0]
            assert "keyword" in data["events"][0]


# ─── 4. Weight Recalculation ───


class TestKeywordWeightRecalc:
    def test_recalc_returns_summary(self):
        from app.db.repo import SupabaseRepo
        from app.services.keyword_weight import recalc_keyword_weights
        result = recalc_keyword_weights(TEST_USER, SupabaseRepo())
        assert "total" in result
        assert "updated" in result
        assert "newly_declining" in result
        assert result["total"] >= 0


# ─── 5. Recommendation Runs & Explanation API ───


class TestRecommendationDebug:
    _run_id: str = ""

    @classmethod
    def _ensure_run(cls):
        if cls._run_id:
            return
        from app.db.repo import SupabaseRepo
        repo = SupabaseRepo()
        snapshot = [{"keyword": "agent memory", "weight": 1.0, "source": "user_explicit"}]
        cls._run_id = repo.insert_recommendation_generation_run(
            user_id=TEST_USER,
            week_start="2026-03-09",
            stage="stage2",
            keyword_snapshot=snapshot,
            candidate_count=5,
            selected_count=3,
            query_text="all:agent+memory",
            selected_urls=["http://arxiv.org/abs/test1", "http://arxiv.org/abs/test2"],
            score_breakdown={
                "avg_base_score": 0.7,
                "avg_keyword_match": 0.05,
                "avg_final_score": 0.75,
                "per_recommendation": [
                    {"url": "http://arxiv.org/abs/test1", "final_score": 0.8, "keyword_match": 0.06, "matched_keywords": [{"keyword": "agent memory", "weight": 1.0, "contribution": "primary"}]},
                    {"url": "http://arxiv.org/abs/test2", "final_score": 0.7, "keyword_match": 0.04, "matched_keywords": []},
                ],
            },
            meta={"prompt_version": "rec-arxiv-v3-keyword"},
        )

    def test_01_list_runs(self):
        self._ensure_run()
        r = client.get("/recommendation-runs")
        assert r.status_code == 200
        data = r.json()
        assert "runs" in data
        assert len(data["runs"]) >= 1

    def test_02_list_runs_filter_stage(self):
        self._ensure_run()
        r = client.get("/recommendation-runs?stage=stage2")
        assert r.status_code == 200
        for run in r.json()["runs"]:
            assert run["stage"] == "stage2"

    def test_03_list_runs_filter_week(self):
        self._ensure_run()
        r = client.get("/recommendation-runs?week_start=2026-03-09")
        assert r.status_code == 200
        data = r.json()
        assert len(data["runs"]) >= 1

    def test_04_explanation_not_found(self):
        r = client.get(f"/recommendations/{uuid.uuid4()}/explanation")
        assert r.status_code == 404
