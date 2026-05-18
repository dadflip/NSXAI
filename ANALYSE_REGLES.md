# Analyse de l'ontologie NSXAI — Nouvelles règles & Feature Engineering

## État des lieux : classes sans individus (gaps actuels)

Les classes suivantes **n'ont aucun individu** dans `instances.owl` original
et méritent attention :

| Groupe | Classes vides |
|--------|--------------|
| Motivationnel SDT | `SDT_Autonomy`, `SDT_Competence`, `SDT_Relatedness`, `Self-Determination_Theory` |
| Modèle Yee | Tous les `Yee_*` (13 sous-classes) |
| Catégories TB | `CategoryCompetition`, `CategoryEffectiveness`, `CategoryEnjoyment`, `CategoryExploration`, `CategoryParticipation`, `CategoryPerformance` |
| Curriculum | `KnowledgeUnit`, `Domain`, `DomainModel`, `Competence`, `Curriculum`, `Context`, `Depth` |
| Resources pédago | Toute la hiérarchie `meututor_domain_resource` (Problem, Activity, Exercise, Hint, …) |
| Player | `Player_Type`, `Player_Action` |
| Erreurs & bugs | `Bug`, `Bug_Misconception`, `Misconception`, `Error`, `Error_Bug`, `Error_Misconception` |

---

## Nouvelles règles SWRL recommandées

### 1. Inférence du profil joueur depuis le comportement archétypal

```
Player(?p) ∧ archetypeBehavior(?p, "competitive") ∧ archetypeBrainRegion(?p, "striatum")
  → isDescribedByType(?p, Conqueror)
```
```
Player(?p) ∧ archetypeBehavior(?p, "cooperative") ∧ archetypeLikes(?p, ?s)
  → isDescribedByType(?p, Socializer)
```
```
Player(?p) ∧ archetypeBehavior(?p, "exploratory")
  → isDescribedByType(?p, Seeker)
```

**Intérêt** : permet de classifier automatiquement de nouveaux joueurs dans le modèle BrainHex
dès que leurs données comportementales sont renseignées — c'est l'une des
règles les plus précieuses pour l'explicabilité neuro-symbolique.

---

### 2. Recommandation GDE selon profil BrainHex

```
GamifiedITS(?its) ∧ hasStudentModel(?its, ?sm) ∧ includes(?sm, ?p)
  ∧ isDescribedByType(?p, Conqueror)
  ∧ DesignPractice(?dp)
  ∧ hasGameElement(?dp, ?gde) ∧ Leaderboards(?gde)
  → recommendedFor(?dp, ?its)
```
```
GamifiedITS(?its) ∧ hasStudentModel(?its, ?sm) ∧ includes(?sm, ?p)
  ∧ isDescribedByType(?p, Socializer)
  ∧ DesignPractice(?dp)
  ∧ hasGameElement(?dp, ?gde) ∧ Teams(?gde)
  → recommendedFor(?dp, ?its)
```
```
GamifiedITS(?its) ∧ hasStudentModel(?its, ?sm) ∧ includes(?sm, ?p)
  ∧ isDescribedByType(?p, Seeker)
  ∧ DesignPractice(?dp) ∧ hasGameElement(?dp, ?gde) ∧ Quests(?gde)
  → recommendedFor(?dp, ?its)
```

**Intérêt** : lie directement les profils joueurs aux éléments de gamification
recommandés — cœur du système de recommandation explicable.

---

### 3. Niveau de difficulté adaptatif via métriques

```
Target_Behavior(?tb) ∧ hasMetric(?tb, ?m)
  ∧ metricValue(?m, ?v) ∧ metricExpectedValue(?m, ?e)
  ∧ swrlb:lessThan(?v, ?e)
  → requiresRemediation(?tb, "true"^^xsd:boolean)
```
```
Target_Behavior(?tb) ∧ hasMetric(?tb, ?m)
  ∧ metricDescription(?m, "error_rate") ∧ metricValue(?m, ?v)
  ∧ swrlb:greaterThan(?v, 0.5)
  → suggestsGDE(?tb, Boss_Fights)   # challenge élevé → boss fight pédagogique
```
```
Target_Behavior(?tb) ∧ hasMetric(?tb, ?m)
  ∧ metricDescription(?m, "completion_rate") ∧ metricValue(?m, ?v)
  ∧ swrlb:greaterThan(?v, 0.9)
  → suggestsGDE(?tb, Badges)        # très bon taux → badge de récompense
```

**Intérêt** : feature engineering clé — on dérive la pertinence des GDE
directement depuis les métriques de performance de l'apprenant.

---

### 4. Classification automatique des ressources pédagogiques

```
Resource(?r) ∧ difficulty(?r, "easy") ∧ type(?r, "video")
  → suitableFor(?r, Seeker)
```
```
Resource(?r) ∧ difficulty(?r, "hard") ∧ type(?r, "interactive")
  → suitableFor(?r, Mastermind)
```
```
Exercise(?e) ∧ difficulty(?e, ?d) ∧ Player(?p) ∧ level(?p, ?d)
  → matchesLevel(?e, ?p)
```

**Intérêt** : permet l'alignement automatique ressource ↔ apprenant sans
intervention manuelle — exploitable par le GNN pour la prédiction de liens.

---

### 5. Règles de qualité de la boucle d'engagement

```
Engagement_Loop(?el) ∧ loopQuality(?el, ?q) ∧ loopStatus(?el, "completed")
  ∧ swrlb:greaterThan(?q, 0.7)
  → isHighQualityLoop(?el, "true"^^xsd:boolean)
```
```
Progressive_Loop(?pl) ∧ loopDifficulty(?pl, ?d)
  ∧ swrlb:lessThan(?d, 0.3)
  → requiresProgression(?pl, "true"^^xsd:boolean)
```

**Intérêt** : pour l'XAI — la qualité d'une boucle d'engagement devient
un signal explicite utilisable dans les explications textuelles.

---

### 6. Modèle SDT : satisfaction des besoins psychologiques

```
Player(?p) ∧ BehaviouralKnowledge(?bk) ∧ hasBehaviouralKnowledge(?sm, ?bk)
  ∧ StudentModel(?sm) ∧ includes(?sm, ?p)
  ∧ rate(?bk, ?r) ∧ swrlb:greaterThan(?r, 0.7)
  ∧ SDT_Competence(?sdt)
  → satisfies(?p, ?sdt)
```
```
Player(?p) ∧ isDescribedByType(?p, Socializer)
  ∧ SDT_Relatedness(?sdt)
  → satisfies(?p, ?sdt)
```

**Intérêt** : raisonnement motivationnel explicite basé sur la Self-Determination
Theory — les explications peuvent citer "ce badge renforce votre besoin de compétence".

---

### 7. Règle de cohérence pédagogique (contrainte OWL)

```
# DisjointClasses : un élément GDE ne peut pas être simultanément
# GDE_Component et GDE_Mechanic (déjà dans l'ontologie)

# Nouvelle contrainte : un ProblemUnit résolu ne peut pas aussi être
# marqué comme nécessitant une remédiation
ProblemUnit(?pu) ∧ isExplained(?pu, true) ∧ requiresRemediation(?pu, true)
  → owl:Nothing   # contradiction → signal pour le raisonneur
```

---

## Feature Engineering pour le GNN

En tenant compte de l'architecture neuro-symbolique (GNN + raisonneur symbolique),
voici les nouvelles **features à dériver** :

### Features nœuds (Player)
| Feature | Dérivation |
|---------|-----------|
| `player_mastery_score` | `mean(metricValue)` sur ses Target_Behaviors |
| `player_engagement_rate` | `count(Engagement_Loop completed) / count(all loops)` |
| `player_error_rate` | `mean(metricValue where metricDescription='error_rate')` |
| `player_progression_speed` | `sum(loopDifficulty) / time_total` |
| `player_social_score` | `count(REF_hasPlayerInteraction) / max_players` |
| `dominant_brainhex_type` | one-hot des 7 archétypes BrainHex |
| `sdt_autonomy_score` | présence de Quests/Exploration GDEs dans DesignPractice |
| `sdt_competence_score` | taux de complétion des loops progressives |

### Features arêtes (DesignPractice → Player)
| Feature | Dérivation |
|---------|-----------|
| `gde_compatibility_score` | cosine_similarity(player BrainHex embedding, GDE embedding) |
| `motivation_coverage` | count(Yee components addressed by GDE) / 13 |
| `difficulty_gap` | abs(player mastery - GDE required level) |
| `historical_effectiveness` | past metricValue improvement after applying this DesignPractice |

### Features nœuds (Resource)
| Feature | Dérivation |
|---------|-----------|
| `resource_engagement_index` | `(numberOfViews + 3*numberOfFavorites) / max_views` |
| `resource_difficulty_match` | match entre `difficulty` resource et `level` player |
| `resource_type_diversity` | entropy sur les types de ressources dans un cours |
| `knowledge_depth_score` | `depth` (surface=0, deep=3) → numérique |

### Features globales (GamifiedITS)
| Feature | Dérivation |
|---------|-----------|
| `loop_quality_avg` | `mean(loopQuality)` de tous les Engagement_Loops |
| `gde_diversity_index` | entropy sur les types de GDE utilisés |
| `player_type_distribution` | histogramme des 7 BrainHex types dans le StudentModel |
| `tb_completion_rate` | Target_Behaviors avec metricValue ≥ metricExpectedValue |

---

## Nouvelles propriétés OWL à ajouter (propositions)

```turtle
# Propriété de recommandation explicite (manquante dans l'ontologie)
:recommendedFor   a owl:ObjectProperty ;
    rdfs:domain :DesignPractice ;
    rdfs:range  :GamifiedITS ;
    rdfs:comment "A DesignPractice is recommended for a given GamifiedITS instance based on player profile." .

# Satisfaction des besoins SDT
:satisfies   a owl:ObjectProperty ;
    rdfs:domain :Player ;
    rdfs:range  :Self-Determination_Theory ;
    rdfs:comment "A player satisfies a psychological need as defined by SDT." .

# Matching ressource-joueur
:matchesLevel   a owl:ObjectProperty ;
    rdfs:domain :Resource ;
    rdfs:range  :Player ;
    rdfs:comment "A resource matches the current skill level of a player." .

# Score de maîtrise (data property manquante)
:masteryScore   a owl:DatatypeProperty ;
    rdfs:domain :Player ;
    rdfs:range  xsd:float ;
    rdfs:comment "Normalized mastery score [0..1] derived from BehaviouralKnowledge metrics." .

# Indice d'engagement calculé
:engagementIndex   a owl:DatatypeProperty ;
    rdfs:domain :Resource ;
    rdfs:range  xsd:float ;
    rdfs:comment "Engagement index derived from views and favorites." .

# Compatibilité GDE-profil
:gdeCompatibilityScore   a owl:DatatypeProperty ;
    rdfs:domain :DesignPractice ;
    rdfs:range  xsd:float ;
    rdfs:comment "Compatibility score between a DesignPractice and target player profile." .
```

---

## Résumé du pipeline de peuplement

```
ontologies/*.owl
       │
       ▼
1_extract_schema.py  ──→  data/schema.json
                     ──→  data/templates/<Classe>.csv  (templates vides)
       │
       ▼
2_populate.py        ──→  data/templates/<Classe>.csv  (remplis, éditables)
       │
   [édition manuelle optionnelle des CSV]
       │
       ▼
3_csv_to_owl.py      ──→  instances.owl  (individus injectés)
```

### Options clés

| Script | Option utile |
|--------|-------------|
| `1_extract_schema.py` | `--onto-dir` pour changer le répertoire des ontologies |
| `2_populate.py` | `--n 50` pour forcer 50 individus par classe ; `--seed` pour reproductibilité |
| `3_csv_to_owl.py` | `--append` pour ajouter sans écraser ; `--also-ttl` pour export Turtle |
