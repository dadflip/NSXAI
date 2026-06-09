"""
Tests for the Gamification API.
Run with: pytest tests/test_api.py -v

Uses a small mock CSV so no real pipeline output is needed.
"""

import pytest
import pandas as pd
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

# ── Build a minimal mock CSV before importing the app ────────────────────────
MOCK_CSV = "/tmp/task4_explanations.csv"

MOCK_DATA = pd.DataFrame([
    {
        "source": "Variables",
        "target": "Level_Up",
        "probability_mean": 0.85,
        "symbolic_confidence": 1.0,
        "neurosymbolic_score": 0.955,
        "confidence_label": "High",
        "path_distance": 1,
        "key_relation": "containsGameElement",
        "ontology_path": "Variables --containsGameElement--> Level_Up",
        "known_positive": True,
        "explanation": "Level_Up is strongly recommended for Variables (score: 0.955).",
    },
    {
        "source": "Variables",
        "target": "BLockGame",
        "probability_mean": 0.72,
        "symbolic_confidence": 0.5,
        "neurosymbolic_score": 0.566,
        "confidence_label": "Moderate",
        "path_distance": 2,
        "key_relation": "hasPreResource",
        "ontology_path": "Variables --hasPreResource--> Task --containsGameElement--> BLockGame",
        "known_positive": False,
        "explanation": "BLockGame is recommended for Variables (score: 0.566).",
    },
    {
        "source": "Loops",
        "target": "Stash",
        "probability_mean": 0.65,
        "symbolic_confidence": 0.5,
        "neurosymbolic_score": 0.545,
        "confidence_label": "Moderate",
        "path_distance": 2,
        "key_relation": "hasPreResource",
        "ontology_path": "Loops --hasPreResource--> Task --containsGameElement--> Stash",
        "known_positive": False,
        "explanation": "Stash is recommended for Loops (score: 0.545).",
    },
])

MOCK_DATA.to_csv(MOCK_CSV, index=False)
os.environ["ARTIFACTS_DIR"] = "/tmp"

# Now import (triggers lifespan which reads the CSV)
from app.main import app

client = TestClient(app, raise_server_exceptions=True)

# Trigger lifespan (loads artifacts) for the whole test session
@pytest.fixture(scope="session", autouse=True)
def start_app():
    with TestClient(app) as c:
        # Patch the module-level client to use the live one
        import tests.test_api as self_module
        self_module.client = c
        yield


# ── Tests ────────────────────────────────────────────────────────────────────

def test_root():
    r = client.get("/")
    assert r.status_code == 200
    assert "service" in r.json()


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["topics"] == 2


def test_list_topics():
    r = client.get("/topics")
    assert r.status_code == 200
    topics = r.json()["topics"]
    assert "Variables" in topics
    assert "Loops" in topics


def test_recommend_basic():
    r = client.get("/recommend/Variables")
    assert r.status_code == 200
    data = r.json()
    assert data["topic"] == "Variables"
    assert len(data["recommendations"]) == 2
    # Sorted by score descending
    scores = [rec["neurosymbolic_score"] for rec in data["recommendations"]]
    assert scores == sorted(scores, reverse=True)


def test_recommend_top_k():
    r = client.get("/recommend/Variables?top_k=1")
    assert r.status_code == 200
    assert len(r.json()["recommendations"]) == 1
    assert r.json()["recommendations"][0]["game_element"] == "Level_Up"


def test_recommend_only_novel():
    r = client.get("/recommend/Variables?only_novel=true")
    assert r.status_code == 200
    recs = r.json()["recommendations"]
    assert all(not rec["is_validated"] for rec in recs)
    assert len(recs) == 1
    assert recs[0]["game_element"] == "BLockGame"


def test_recommend_min_score():
    r = client.get("/recommend/Variables?min_score=0.9")
    assert r.status_code == 200
    recs = r.json()["recommendations"]
    assert all(rec["neurosymbolic_score"] >= 0.9 for rec in recs)


def test_recommend_case_insensitive():
    r = client.get("/recommend/variables")
    assert r.status_code == 200


def test_recommend_not_found():
    r = client.get("/recommend/UnknownTopic")
    assert r.status_code == 404
    assert "did_you_mean" in r.json()["detail"]


def test_recommend_batch():
    r = client.post("/recommend/batch", json={"topics": ["Variables", "Loops"], "top_k": 2})
    assert r.status_code == 200
    results = r.json()["results"]
    assert "Variables" in results
    assert "Loops" in results
    assert len(results["Variables"]) <= 2


def test_recommend_batch_unknown():
    r = client.post("/recommend/batch", json={"topics": ["Ghost"], "top_k": 3})
    assert r.status_code == 200
    assert r.json()["results"]["Ghost"]["error"] == "not found"


def test_element_endpoint():
    r = client.get("/element/Level_Up")
    assert r.status_code == 200
    data = r.json()
    assert data["game_element"] == "Level_Up"
    assert len(data["recommended_for"]) >= 1


def test_stats():
    r = client.get("/stats")
    assert r.status_code == 200
    s = r.json()
    assert s["total_recommendations"] == 3
    assert s["validated_links"] == 1
    assert s["novel_links"] == 2


def test_recommendation_fields():
    """Verify all expected fields are present in a recommendation."""
    r = client.get("/recommend/Variables")
    rec = r.json()["recommendations"][0]
    expected_fields = {
        "game_element", "neurosymbolic_score", "neural_probability",
        "symbolic_confidence", "confidence_label", "path_distance",
        "key_relation", "ontology_path", "is_validated", "explanation"
    }
    assert expected_fields.issubset(set(rec.keys()))
