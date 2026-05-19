#!/usr/bin/env python3
"""
2_populate.py
=============
Lit data/schema.json et génère des individus synthétiques réalistes
dans les fichiers data/templates/<Classe>.csv.

Stratégie de peuplement :
  1. Les classes feuilles concrètes sont peuplées en premier.
  2. Les références (REF_*) sont résolues en piochant dans les IDs déjà générés.
  3. Les valeurs littérales sont tirées de domaines métier cohérents.

Modifications v2 :
  - Générateurs spécialisés pour les classes précédemment vides :
    SDT_Autonomy/Competence/Relatedness, Yee_*, CategoryXxx,
    Resource, Problem, Activity, Exercise, Hint, Curriculum, Domain,
    KnowledgeUnit, Player_Type, Player_Action, Bug, Misconception, Error.
  - Générateurs pour les nouvelles propriétés de recommandation :
    masteryScore, engagementIndex, gdeCompatibilityScore,
    REF_recommendedFor, REF_satisfies, REF_matchesLevel.
  - DEFAULT_COUNTS mis à jour pour inclure toutes les classes manquantes.

Usage:
    python 2_populate.py [--schema data/schema.json] [--out-dir data/templates]
                         [--n <count_per_class>] [--seed 42]

Dépendances: aucune (stdlib uniquement)
"""

import argparse, csv, json, os, random, re
from datetime import date, timedelta
from collections import defaultdict

# ══════════════════════════════════════════════════════════════════════════════
#  Domain-aware value generators
# ══════════════════════════════════════════════════════════════════════════════

RNG = random.Random(42)

SUBJECTS = [
    "Mathematics", "Physics", "Chemistry", "Biology", "History",
    "Geography", "Literature", "Computer Science", "Economics",
    "Philosophy", "Statistics", "Data Science", "Algebra", "Calculus",
]

DIFFICULTY_LEVELS      = ["easy", "medium", "hard", "expert"]
ARCHETYPE_BEHAVIORS    = ["competitive", "cooperative", "exploratory", "social", "achiever", "survivor"]
ARCHETYPE_BRAIN_REGIONS= ["hippocampus", "prefrontal", "amygdala", "striatum", "cerebellum"]
ARCHETYPE_LIKES        = SUBJECTS
ARCHETYPE_MESSENGERS   = ["dopamine", "serotonin", "norepinephrine", "acetylcholine", "oxytocin"]

METRIC_DESCRIPTIONS = [
    "error_rate", "score", "completion_rate", "time_on_task", "hint_usage",
    "attempt_count", "correct_answers", "engagement_score", "mastery_level",
    "progress_ratio", "streak_count", "xp_earned",
]

STRATEGIES      = ["mastery", "remediation", "exploration", "challenge", "scaffolding"]
TACTICS         = ["hint_first", "example_first", "test_first", "review_first", "spaced_repetition"]
STRATEGY_TYPES  = ["adaptive", "fixed", "mixed"]
TACTIC_TYPES    = ["formative", "summative", "diagnostic"]
ASSESSMENT_TYPES= ["quiz", "exercise", "project", "exam", "peer_review"]
RESOURCE_TYPES  = ["video", "text", "interactive", "quiz", "simulation", "infographic", "podcast"]
LOOP_STATUSES   = ["active", "completed", "pending", "paused"]

TEACHER_NAMES = [
    "Prof. Martin", "Dr. Dupont", "Prof. Schmidt", "Dr. Chen",
    "Prof. García", "Dr. Johnson", "Prof. Rossi",
]

COURSE_NAMES = (
    [f"Introduction to {s}" for s in SUBJECTS] +
    [f"Advanced {s}"        for s in SUBJECTS[:7]] +
    ["Research Methods", "Critical Thinking", "Project Management"]
)

KU_DESCRIPTIONS = (
    [f"Understanding {s} fundamentals" for s in SUBJECTS] +
    ["Problem solving strategies", "Conceptual reasoning",
     "Applied methodology", "Practical exercises",
     "Case study analysis", "Formative evaluation"]
)

CONTEXT_TYPES = ["individual", "collaborative", "competitive", "blended"]
DEPTH_LEVELS  = ["surface", "conceptual", "procedural", "deep"]
PROBLEM_TYPES = [
    "multiple_choice", "fill_blank", "true_false", "match_column",
    "open_question", "discursive",
]

BUG_DESCRIPTIONS = [
    "Off-by-one error", "Sign error", "Unit confusion",
    "Formula inversion", "Concept conflation", "Causal reversal",
]
MISCONCEPTIONS = [
    "Correlation implies causation", "Heavier objects fall faster",
    "Photosynthesis happens only in light", "Heat and temperature are the same",
    "Evolution is goal-directed",
]
COMMENT_TEXTS = [
    "Good explanation", "Needs more examples", "Too abstract",
    "Very clear", "Challenging but rewarding", "Could be improved",
]
URI_TYPES = ["video", "pdf", "html", "interactive", "external_link"]

# ── SDT / Yee / Category specific labels ─────────────────────────────────────

SDT_NAMES = {
    "SDT_Autonomy":   ["autonomy_low", "autonomy_medium", "autonomy_high"],
    "SDT_Competence": ["competence_low", "competence_medium", "competence_high"],
    "SDT_Relatedness":["relatedness_low", "relatedness_medium", "relatedness_high"],
}

YEE_COMPONENT_NAMES = {
    "Yee_Achievement_Component": ["achievement_alpha", "achievement_beta", "achievement_gamma"],
    "Yee_Immersion_Component":   ["immersion_alpha", "immersion_beta", "immersion_gamma"],
    "Yee_Social_Component":      ["social_alpha", "social_beta", "social_gamma"],
    "Yee_Advancement":  ["advancement_low", "advancement_mid", "advancement_high"],
    "Yee_Competition":  ["competition_low", "competition_mid", "competition_high"],
    "Yee_Mechanics":    ["mechanics_basic", "mechanics_mid", "mechanics_advanced"],
    "Yee_Customization":["customization_low", "customization_mid", "customization_high"],
    "Yee_Discovery":    ["discovery_low", "discovery_mid", "discovery_high"],
    "Yee_Escapism":     ["escapism_low", "escapism_mid", "escapism_high"],
    "Yee_Relationship": ["relationship_low", "relationship_mid", "relationship_high"],
    "Yee_Socializing":  ["socializing_low", "socializing_mid", "socializing_high"],
    "Yee_Teamwork":     ["teamwork_low", "teamwork_mid", "teamwork_high"],
}

CATEGORY_LABELS = {
    "CategoryCompetition":   ["competition_low", "competition_medium", "competition_high"],
    "CategoryEffectiveness": ["effectiveness_low", "effectiveness_medium", "effectiveness_high"],
    "CategoryEnjoyment":     ["enjoyment_low", "enjoyment_medium", "enjoyment_high"],
    "CategoryExploration":   ["exploration_low", "exploration_medium", "exploration_high"],
    "CategoryParticipation": ["participation_low", "participation_medium", "participation_high"],
    "CategoryPerformance":   ["performance_low", "performance_medium", "performance_high"],
}

# BrainHex archetype → expected archetype behavior (for coherent profiling)
BRAINHEX_ARCHETYPES = {
    "Achiever":   "achiever",
    "Conqueror":  "competitive",
    "Daredevil":  "competitive",
    "Mastermind": "exploratory",
    "Seeker":     "exploratory",
    "Socializer": "cooperative",
    "Survivor":   "survivor",
}

# ── Player action types ───────────────────────────────────────────────────────
PLAYER_ACTION_TYPES = [
    "submit_answer", "view_resource", "request_hint",
    "complete_exercise", "join_team", "earn_badge",
    "level_up", "start_quest", "finish_quest",
    "give_feedback", "rate_content", "help_peer",
]

# ══════════════════════════════════════════════════════════════════════════════
#  Generator functions per property name / type
# ══════════════════════════════════════════════════════════════════════════════

def gen_value(prop_name: str, range_type: str, class_name: str = "") -> str:
    """Return a realistic value for a data property."""
    p   = prop_name.lower()
    cls = class_name.lower()

    # ── numeric ────────────────────────────────────────────────────────────
    if range_type.startswith("float"):
        # Derived recommendation scores [0..1]
        if p in ("masteryscore", "engagementindex", "gdecompatibilityscore"):
            return str(round(RNG.uniform(0.1, 1.0), 3))
        if "0..1" in range_type or "quality" in p or "rate" in p or "score" in p:
            return str(round(RNG.uniform(0.0, 1.0), 3))
        if "difficulty" in p or "weight" in p:
            return str(round(RNG.uniform(0.1, 1.0), 2))
        if "expected" in p or "metric" in p:
            return str(round(RNG.uniform(10.0, 100.0), 2))
        if "value" in p:
            return str(round(RNG.uniform(0.0, 100.0), 2))
        if "score" in p:
            return str(round(RNG.uniform(0.0, 20.0), 2))
        if "mean" in p or "deviation" in p:
            return str(round(RNG.uniform(0.5, 5.0), 3))
        return str(round(RNG.uniform(0.0, 100.0), 2))

    if range_type == "int":
        if "order" in p or "step" in p or "precedence" in p:
            return str(RNG.randint(1, 10))
        if "view" in p or "favorite" in p:
            return str(RNG.randint(0, 500))
        if "size" in p:
            return str(RNG.randint(1, 50))
        return str(RNG.randint(1, 100))

    if range_type == "bool":
        return RNG.choice(["True", "False"])

    if range_type == "date":
        base  = date(2023, 1, 1)
        delta = RNG.randint(0, 700)
        return str(base + timedelta(days=delta))

    # ── string ────────────────────────────────────────────────────────────

    # Derived recommendation scores stored as strings in some edge cases
    if p in ("masteryscore", "engagementindex", "gdecompatibilityscore"):
        return str(round(RNG.uniform(0.1, 1.0), 3))

    if "archetype" in p:
        if "behavior" in p:  return RNG.choice(ARCHETYPE_BEHAVIORS)
        if "brain" in p:     return RNG.choice(ARCHETYPE_BRAIN_REGIONS)
        if "likes" in p:     return RNG.choice(ARCHETYPE_LIKES)
        if "chemical" in p:  return RNG.choice(ARCHETYPE_MESSENGERS)

    # SDT / Yee / Category label fields
    if p in ("competionname", "effectivenessname", "enjoymentname",
             "explorationname", "participationname", "performancename"):
        return p.replace("name", "_") + str(RNG.randint(1, 5))

    if "metricdescription" in p or "description" in p:
        return RNG.choice(METRIC_DESCRIPTIONS)

    if "strategy" in p and "type" in p:
        return RNG.choice(STRATEGY_TYPES)
    if "tactic" in p and "type" in p:
        return RNG.choice(TACTIC_TYPES)
    if "assessment" in p:
        return RNG.choice(ASSESSMENT_TYPES)
    if "strategy" in p:
        return RNG.choice(STRATEGIES)
    if "tactic" in p:
        return RNG.choice(TACTICS)

    if "coursename" in p or "title" in p:
        return RNG.choice(COURSE_NAMES)
    if "teacher" in p:
        return RNG.choice(TEACHER_NAMES)

    if "type" in p:
        if "resource" in p or "uri" in p:  return RNG.choice(RESOURCE_TYPES)
        if "problem" in p:                 return RNG.choice(PROBLEM_TYPES)
        if "context" in p:                 return RNG.choice(CONTEXT_TYPES)
        return RNG.choice(["typeA", "typeB", "typeC"])

    if "level" in p:
        return RNG.choice(DIFFICULTY_LEVELS)

    if "domain" in p or "subject" in p:
        return RNG.choice(SUBJECTS)

    if "statement" in p or "question" in p or "hint" in p:
        return f"Sample {prop_name} text #{RNG.randint(1, 999)}"

    if "comment" in p:
        return RNG.choice(COMMENT_TEXTS)

    if "difficulty" in p:
        return RNG.choice(DIFFICULTY_LEVELS)

    if "status" in p:
        return RNG.choice(LOOP_STATUSES)

    if "cluster" in p:
        return f"cluster_{RNG.randint(1, 5)}"

    if "duration" in p or "time" in p:
        return str(RNG.randint(5, 120))

    if "name" in p:
        return f"{prop_name}_{RNG.randint(1, 99):02d}"

    if "term" in p:
        return RNG.choice(SUBJECTS).lower().replace(" ", "_")

    if "issue" in p or "error" in p:
        return RNG.choice(BUG_DESCRIPTIONS)

    if "misconception" in p:
        return RNG.choice(MISCONCEPTIONS)

    if "date" in p or "posting" in p:
        return str(date(2023, RNG.randint(1, 12), RNG.randint(1, 28)))

    if "order" in p:
        return str(RNG.randint(1, 20))

    if "weight" in p or "rate" in p or "value" in p:
        return str(round(RNG.uniform(0.0, 1.0), 3))

    # Fallback
    return f"{prop_name}_value_{RNG.randint(1, 999)}"


# ── Specialised per-class row enrichment ──────────────────────────────────────

def enrich_row(cname: str, row: dict, cols: list, id_pool: dict) -> None:
    """
    Apply class-specific coherent overrides after generic gen_value pass.
    Modifies row in-place.
    """
    # BrainHex sub-types: archetype behavior should match the type
    if cname in BRAINHEX_ARCHETYPES and "archetypeBehavior" in row:
        row["archetypeBehavior"] = BRAINHEX_ARCHETYPES[cname]

    # SDT classes: set a meaningful label via their name-property if present
    if cname in SDT_NAMES:
        labels = SDT_NAMES[cname]
        for col in cols:
            if col in ("description", "title", "name") and col in row:
                row[col] = RNG.choice(labels)
                break

    # Yee classes: same
    if cname in YEE_COMPONENT_NAMES:
        labels = YEE_COMPONENT_NAMES[cname]
        for col in cols:
            if col in ("description", "title", "name") and col in row:
                row[col] = RNG.choice(labels)
                break

    # Category classes: use dedicated name fields
    if cname in CATEGORY_LABELS:
        labels = CATEGORY_LABELS[cname]
        for col in cols:
            if col.endswith("Name") and col in row:
                row[col] = RNG.choice(labels)

    # Resource: ensure difficulty and level are set + engagementIndex
    if cname == "Resource":
        if "difficulty" in row:
            row["difficulty"] = RNG.choice(DIFFICULTY_LEVELS)
        if "level" in row:
            row["level"] = RNG.choice(DIFFICULTY_LEVELS)
        if "numberOfViews" in row:
            row["numberOfViews"] = str(RNG.randint(10, 1000))
        if "numberOfFavorites" in row:
            row["numberOfFavorites"] = str(RNG.randint(0, 200))
        if "engagementIndex" in row:
            views = int(row.get("numberOfViews", "50"))
            favs  = int(row.get("numberOfFavorites", "10"))
            idx   = min(1.0, (views + 3 * favs) / 1500)
            row["engagementIndex"] = str(round(idx, 3))

    # Player: masteryScore derived from metrics (simulated)
    if cname == "Player":
        if "masteryScore" in row:
            row["masteryScore"] = str(round(RNG.uniform(0.2, 1.0), 3))
        if "archetypeBehavior" in row:
            row["archetypeBehavior"] = RNG.choice(ARCHETYPE_BEHAVIORS)

    # DesignPractice: gdeCompatibilityScore
    if cname == "DesignPractice":
        if "gdeCompatibilityScore" in row:
            row["gdeCompatibilityScore"] = str(round(RNG.uniform(0.3, 1.0), 3))

    # Engagement_Loop: loopQuality and loopStatus should be coherent
    if cname == "Engagement_Loop":
        status = RNG.choice(LOOP_STATUSES)
        if "loopStatus" in row:
            row["loopStatus"] = status
        if "loopQuality" in row:
            # completed loops tend to have higher quality
            row["loopQuality"] = str(round(
                RNG.uniform(0.5, 1.0) if status == "completed" else RNG.uniform(0.1, 0.7),
                3
            ))

    # Progressive_Loop: loopDifficulty progressive
    if cname == "Progressive_Loop":
        if "loopDifficulty" in row:
            row["loopDifficulty"] = str(round(RNG.uniform(0.1, 0.9), 2))

    # Metric: metricValue should be close to but sometimes below metricExpectedValue
    if cname == "Metric":
        expected = round(RNG.uniform(10.0, 90.0), 2)
        actual   = round(expected * RNG.uniform(0.5, 1.2), 2)
        if "metricExpectedValue" in row:
            row["metricExpectedValue"] = str(expected)
        if "metricValue" in row:
            row["metricValue"] = str(actual)
        if "metricDescription" in row:
            row["metricDescription"] = RNG.choice(METRIC_DESCRIPTIONS)

    # Player_Action: type should use dedicated list
    if cname == "Player_Action":
        if "type" in row:
            row["type"] = RNG.choice(PLAYER_ACTION_TYPES)

    # Bug / Error / Misconception: description
    if cname in ("Bug", "Bug_Misconception", "Error_Bug"):
        if "description" in row:
            row["description"] = RNG.choice(BUG_DESCRIPTIONS)
        if "issue" in row:
            row["issue"] = RNG.choice(BUG_DESCRIPTIONS)
    if cname in ("Misconception", "Error_Misconception"):
        if "description" in row:
            row["description"] = RNG.choice(MISCONCEPTIONS)

    # KnowledgeUnit / Competence: description
    if cname in ("KnowledgeUnit", "Competence", "Domain", "Curriculum"):
        if "description" in row:
            row["description"] = RNG.choice(KU_DESCRIPTIONS)
        if "title" in row:
            row["title"] = RNG.choice(COURSE_NAMES)

    # Context: type field
    if cname == "Context":
        if "type" in row:
            row["type"] = RNG.choice(CONTEXT_TYPES)

    # Depth
    if cname == "Depth":
        if "level" in row:
            row["level"] = RNG.choice(DEPTH_LEVELS)


# ══════════════════════════════════════════════════════════════════════════════
#  Reference resolution
# ══════════════════════════════════════════════════════════════════════════════

def pick_ref(target_classes: list, id_pool: dict) -> str:
    """Pick one or more IDs from the pool for a reference property."""
    candidates = []
    for tc in target_classes:
        candidates.extend(id_pool.get(tc, []))
    if not candidates:
        return ""
    n = RNG.randint(1, min(3, len(candidates)))
    picked = RNG.sample(candidates, n)
    return "|".join(picked)

# ══════════════════════════════════════════════════════════════════════════════
#  Populate counts per class
# ══════════════════════════════════════════════════════════════════════════════

DEFAULT_COUNTS = {
    # ── Gamification core ──────────────────────────────────────────────────
    "Player":              20,
    "StudentModel":        20,
    "BrainHex":            20,
    "Achiever":             5,
    "Conqueror":            5,
    "Daredevil":            5,
    "Mastermind":           5,
    "Seeker":               5,
    "Socializer":           5,
    "Survivor":             5,
    "GamificationModel":   10,
    "GamifiedITS":         10,
    "DesignPractice":      10,
    "Engagement_Loop":     10,
    "Progressive_Loop":    10,
    "Target_Behavior":     40,
    "Metric":              60,
    # ── GDE Components ────────────────────────────────────────────────────
    "Badges":               5,
    "Points":               5,
    "Achievements":         5,
    "Leaderboards":         5,
    "Levels":               5,
    "Quests":               5,
    "Rewards":              5,
    "Challenges":           5,
    "Boss_Fights":          5,
    "Avatars":              5,
    "Status":               5,
    "Story":                5,
    "Theme":                5,
    "Teams":                5,
    "Feedback":             5,
    "Social_Graph":         5,
    "Win_States":           5,
    "Collections":          5,
    "Competition":          5,
    "Cooperation":          5,
    "Chances":              5,
    "Combat":               5,
    "Content_Unlocking":    5,
    "Constraints":          5,
    "Emotions":             5,
    "Gifting":              5,
    "Narrative":            5,
    "Progression":          5,
    "Relationships":        5,
    "Resource_Acquisition": 5,
    "Time_Constraints":     5,
    "Transactions":         5,
    "Turns":                5,
    "Virtual_Goods":        5,
    # ── SDT (previously empty) ────────────────────────────────────────────
    "SDT_Autonomy":          5,
    "SDT_Competence":        5,
    "SDT_Relatedness":       5,
    # ── Yee motivational components (previously empty) ────────────────────
    "Yee_Achievement_Component": 3,
    "Yee_Immersion_Component":   3,
    "Yee_Social_Component":      3,
    "Yee_Advancement":       3,
    "Yee_Competition":       3,
    "Yee_Mechanics":         3,
    "Yee_Customization":     3,
    "Yee_Discovery":         3,
    "Yee_Escapism":          3,
    "Yee_Relationship":      3,
    "Yee_Socializing":       3,
    "Yee_Teamwork":          3,
    # ── Target behavior categories (previously empty) ─────────────────────
    "CategoryCompetition":   3,
    "CategoryEffectiveness": 3,
    "CategoryEnjoyment":     3,
    "CategoryExploration":   3,
    "CategoryParticipation": 3,
    "CategoryPerformance":   3,
    # ── Pedagogical ───────────────────────────────────────────────────────
    "Course":              10,
    "DomainModel":         10,
    "Domain":              10,          # previously empty
    "Competence":          20,          # previously empty
    "Curriculum":          10,          # previously empty
    "Context":              5,          # previously empty
    "Depth":                5,          # previously empty
    "InstrutionalPlan":    20,
    "Strategy":            20,
    "Tactic":              20,
    "Sequencing":          20,
    "ProblemUnit":         20,
    "ResourceUnit":        20,
    "ProblemNext":         20,
    "CurriculumUnit":       5,
    "BehaviouralKnowledge": 20,
    "PedagogicalModel":     5,
    "KnowledgeUnit":       20,          # previously empty
    "PedagogicalUnit":     10,
    "ConceptualKnowledge": 10,
    "GenericOperator":      5,
    "UniversalGenericOperator": 3,
    "CKCurriculumInformation": 10,
    "Catalogue":            5,
    "ResourceWeight":      10,
    # ── Resources (previously empty hierarchy) ────────────────────────────
    "Resource":            20,
    "Problem":             20,
    "Activity":            20,
    "Exercise":            20,
    "Concept":             10,
    "Content":             10,
    "Question":            20,
    "Hint":                10,          # previously empty
    "Comment":             10,
    "Diagnosis":           10,
    "Statement":           15,
    "Resolution":          15,
    "ResolutionMethod":    10,
    "MethodStep":          10,
    "URIResource":         10,
    "URIType":              5,
    "Form":                 5,
    "ResourceList":         5,
    "CompositeResource":    5,
    "EvaluationResource":   5,
    "ProblemBasedEvaluation": 5,
    "WritingEvaluation":    5,
    "MultipleChoiceProblem": 10,
    "MultipleChoiceOption":  20,
    "TrueOrFalseProblem":    10,
    "TrueOrFalseOption":     10,
    "FillBlanksProblem":     10,
    "FillBlanksOption":      10,
    "MatchColumnProblem":    10,
    "MatchColumnOption":     10,
    "MatchColumnAnswer":     10,
    "DiscursiveProblem":      5,
    "DiscursiveOption":      10,
    "LeftColumn":            10,
    "RightColumn":           10,
    "Option":                20,
    # ── Errors & Bugs (previously empty) ─────────────────────────────────
    "Bug":                  5,
    "Bug_Misconception":    5,
    "Misconception":        5,
    "Error":                5,
    "Error_Bug":            5,
    "Error_Misconception":  5,
    # ── Player model (previously empty) ──────────────────────────────────
    "Player_Type":           7,
    "Player_Action":        20,
    # ── Motivation ────────────────────────────────────────────────────────
    "Motivation":            5,
    "Motivational_Affordance": 5,
    # ── SIOC ──────────────────────────────────────────────────────────────
    "UserAccount":          10,
    "Item":                  5,
    "Container":             3,
}

# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════

def safe_name(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_]', '_', name)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema",  default="data/schema.json")
    parser.add_argument("--out-dir", default="data/templates")
    parser.add_argument("--n",       type=int, default=0,
                        help="Override count for every class (0 = use per-class defaults)")
    parser.add_argument("--seed",    type=int, default=42)
    args = parser.parse_args()

    RNG.seed(args.seed)
    random.seed(args.seed)

    schema_path = os.path.abspath(args.schema)
    out_dir     = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)

    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)

    classes = schema["classes"]

    # Topological order: fewer object-prop dependencies first
    def ref_count(cinfo):
        return sum(1 for _ in cinfo["object_props"])

    ordered = sorted(
        [(cname, cinfo) for cname, cinfo in classes.items() if not cinfo["is_abstract"]],
        key=lambda x: ref_count(x[1])
    )

    id_pool: dict[str, list[str]] = defaultdict(list)

    for cname, cinfo in ordered:
        n      = args.n if args.n > 0 else DEFAULT_COUNTS.get(cname, 5)
        prefix = cinfo["id_prefix"]

        fname = safe_name(cname) + ".csv"
        fpath = os.path.join(out_dir, fname)
        if not os.path.exists(fpath):
            print(f"  [SKIP] {fname} not found (run 1_extract_schema.py first)")
            continue

        # Read existing header (skip comment lines)
        with open(fpath, "r", encoding="utf-8") as f:
            raw_lines = f.readlines()

        header_line   = None
        comment_lines = []
        for line in raw_lines:
            if line.startswith("#"):
                comment_lines.append(line)
            elif header_line is None:
                header_line = line.strip()

        if not header_line:
            print(f"  [WARN] No header in {fname}, skipping")
            continue

        cols = [c.strip() for c in header_line.split(",")]

        # Generate n individuals
        rows = []
        for i in range(1, n + 1):
            ind_id = f"{prefix}_{i:04d}"
            id_pool[cname].append(ind_id)
            row = {"id": ind_id}

            # Generic value generation
            for col in cols[1:]:
                if col.startswith("REF_"):
                    prop_name = col[4:]
                    op_info   = cinfo["object_props"].get(prop_name, {})
                    targets   = op_info.get("range", [])
                    row[col]  = pick_ref(targets, id_pool)
                else:
                    dp_info  = cinfo["data_props"].get(col, {})
                    rtype    = dp_info.get("range_type", "str")
                    row[col] = gen_value(col, rtype, cname)

            # Class-specific coherent overrides
            enrich_row(cname, row, cols, id_pool)

            rows.append(row)

        # Rewrite file: comments + header + data rows
        with open(fpath, "w", newline="", encoding="utf-8") as f:
            f.writelines(comment_lines)
            writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

        print(f"  [OK] {fname}: {n} individuals")

    total = sum(len(v) for v in id_pool.values())
    print(f"\n  Done. id_pool: {total} individuals across {len(id_pool)} classes.")
    print("  Next step: python 3_csv_to_owl.py")

if __name__ == "__main__":
    main()
