"""
Gamification Recommendation API
Serves neuro-symbolic recommendations from task4_explanations.csv
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import pandas as pd
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Global state ────────────────────────────────────────────────────────────
DATA: dict = {}

ARTIFACTS_DIR = os.getenv("ARTIFACTS_DIR", "./artifacts")


def load_artifacts():
    """Load CSV artifacts into memory at startup."""
    explanations_path = os.path.join(ARTIFACTS_DIR, "task4_explanations.csv")
    if not os.path.exists(explanations_path):
        raise FileNotFoundError(
            f"task4_explanations.csv not found at {explanations_path}\n"
            f"Run the pipeline first or set ARTIFACTS_DIR env var."
        )

    df = pd.read_csv(explanations_path)

    # Normalize column names (strip whitespace)
    df.columns = df.columns.str.strip()

    # Ensure required columns exist
    required = {
        "source", "target", "probability_mean", "symbolic_confidence",
        "neurosymbolic_score", "confidence_label", "path_distance",
        "key_relation", "ontology_path", "known_positive", "explanation"
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in CSV: {missing}")

    df["source"]         = df["source"].astype(str).str.strip()
    df["target"]         = df["target"].astype(str).str.strip()
    df["known_positive"] = df["known_positive"].astype(bool)

    DATA["df"]     = df
    DATA["topics"] = sorted(df["source"].unique().tolist())
    DATA["elements"] = sorted(df["target"].unique().tolist())

    logger.info(
        f"Loaded {len(df)} recommendations | "
        f"{len(DATA['topics'])} topics | "
        f"{len(DATA['elements'])} game elements"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_artifacts()
    yield
    DATA.clear()


# ── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Gamification Recommendation API",
    description=(
        "Neuro-symbolic recommendations linking Java topics to game elements. "
        "Based on GCN/GraphSAGE predictions filtered and ranked by ontology (SWRL/OWL)."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # restrict in production
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── Helpers ──────────────────────────────────────────────────────────────────
def row_to_recommendation(row: pd.Series) -> dict:
    return {
        "game_element":        row["target"],
        "neurosymbolic_score": round(float(row["neurosymbolic_score"]), 4),
        "neural_probability":  round(float(row["probability_mean"]), 4),
        "symbolic_confidence": round(float(row["symbolic_confidence"]), 4),
        "confidence_label":    row["confidence_label"],
        "path_distance":       int(row["path_distance"]),
        "key_relation":        row["key_relation"],
        "ontology_path":       row["ontology_path"],
        "is_validated":        bool(row["known_positive"]),
        "explanation":         row["explanation"],
    }


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/", tags=["meta"])
def root():
    return {
        "service": "Gamification Recommendation API",
        "version": "1.0.0",
        "docs":    "/docs",
        "health":  "/health",
    }


@app.get("/health", tags=["meta"])
def health():
    if "df" not in DATA:
        raise HTTPException(503, "Artifacts not loaded")
    return {
        "status":       "ok",
        "topics":       len(DATA["topics"]),
        "elements":     len(DATA["elements"]),
        "total_recommendations": len(DATA["df"]),
    }


@app.get("/topics", tags=["discovery"])
def list_topics():
    """Return all available Java topics."""
    return {"topics": DATA["topics"], "count": len(DATA["topics"])}


@app.get("/elements", tags=["discovery"])
def list_elements():
    """Return all available game elements."""
    return {"elements": DATA["elements"], "count": len(DATA["elements"])}


@app.get("/recommend/{topic}", tags=["recommend"])
def recommend(
    topic: str,
    top_k: int  = Query(5,  ge=1, le=20,  description="Max recommendations to return"),
    min_score: float = Query(0.0, ge=0.0, le=1.0, description="Minimum neuro-symbolic score"),
    only_novel: bool = Query(False, description="Exclude already validated links"),
):
    """
    Get top-K game element recommendations for a Java topic.

    - **topic**: exact label (e.g. `Variables`, `Loops`)
    - **top_k**: number of results (default 5, max 20)
    - **min_score**: filter by minimum neuro-symbolic score
    - **only_novel**: if true, exclude links already in the ontology
    """
    df = DATA["df"]

    matches = df[df["source"].str.lower() == topic.strip().lower()]
    if matches.empty:
        close = [t for t in DATA["topics"] if topic.lower() in t.lower()]
        raise HTTPException(
            404,
            detail={
                "error":      f"Topic '{topic}' not found.",
                "did_you_mean": close[:5],
                "all_topics": DATA["topics"],
            }
        )

    if only_novel:
        matches = matches[~matches["known_positive"]]

    matches = (
        matches[matches["neurosymbolic_score"] >= min_score]
        .sort_values("neurosymbolic_score", ascending=False)
        .head(top_k)
    )

    return {
        "topic":           matches.iloc[0]["source"],
        "count":           len(matches),
        "filters":         {"top_k": top_k, "min_score": min_score, "only_novel": only_novel},
        "recommendations": [row_to_recommendation(row) for _, row in matches.iterrows()],
    }


@app.post("/recommend/batch", tags=["recommend"])
def recommend_batch(payload: dict):
    """
    Get recommendations for multiple topics at once.

    Body: `{"topics": ["Variables", "Loops", "Arrays"], "top_k": 3}`
    """
    topics = payload.get("topics", [])
    top_k  = int(payload.get("top_k", 5))

    if not topics:
        raise HTTPException(400, "Provide a non-empty 'topics' list.")
    if len(topics) > 50:
        raise HTTPException(400, "Max 50 topics per batch request.")

    results = {}
    df = DATA["df"]

    for topic in topics:
        matches = df[df["source"].str.lower() == topic.strip().lower()]
        if matches.empty:
            results[topic] = {"error": "not found"}
        else:
            rows = matches.sort_values("neurosymbolic_score", ascending=False).head(top_k)
            results[topic] = [row_to_recommendation(r) for _, r in rows.iterrows()]

    return {"results": results, "top_k": top_k}


@app.get("/element/{element}", tags=["discovery"])
def topics_for_element(element: str):
    """Which Java topics recommend a given game element?"""
    df = DATA["df"]
    matches = df[df["target"].str.lower() == element.strip().lower()]
    if matches.empty:
        raise HTTPException(404, f"Game element '{element}' not found.")

    rows = matches.sort_values("neurosymbolic_score", ascending=False)
    return {
        "game_element": rows.iloc[0]["target"],
        "recommended_for": [
            {
                "topic": row["source"],
                "neurosymbolic_score": round(float(row["neurosymbolic_score"]), 4),
                "explanation": row["explanation"],
            }
            for _, row in rows.iterrows()
        ]
    }


@app.get("/stats", tags=["meta"])
def stats():
    """Summary statistics of the recommendation dataset."""
    df = DATA["df"]
    return {
        "total_recommendations": len(df),
        "topics":                len(df["source"].unique()),
        "game_elements":         len(df["target"].unique()),
        "validated_links":       int(df["known_positive"].sum()),
        "novel_links":           int((~df["known_positive"]).sum()),
        "confidence_distribution": df["confidence_label"].value_counts().to_dict(),
        "score_stats": {
            "mean":  round(float(df["neurosymbolic_score"].mean()), 4),
            "max":   round(float(df["neurosymbolic_score"].max()), 4),
            "min":   round(float(df["neurosymbolic_score"].min()), 4),
        },
    }
