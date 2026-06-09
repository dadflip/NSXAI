import React, { useState, useEffect, useMemo } from 'react';
import { Download, PlugZap, CheckCircle2, Server, FileJson, FileSpreadsheet, Share2, Database, Activity, BrainCircuit, FileText, GitBranch, BarChart2, Layers, AlignLeft } from 'lucide-react';
import { apiUrl } from '../config';
import { fetchApi } from '../lib/apiClient';
import { CONFIG } from '../config';

interface ExportOption {
    title: string;
    description: string;
    endpoint: string;
    filename: string;
    icon: React.ReactNode;
    color: string;
    readme: string;
}

interface ExportCardProps {
    option: ExportOption;
    exporting: boolean;
    onExport: (endpoint: string, filename: string) => void;
    onReadme: (option: ExportOption) => void;
}

const ExportCard: React.FC<ExportCardProps> = ({ option, exporting, onExport, onReadme }) => (
    <div className="group bg-white/[0.02] hover:bg-white/[0.04] p-5 rounded-2xl border border-white/[0.05] flex flex-col justify-between gap-4 transition-all duration-300">
        <div className="flex items-start gap-3.5">
            <div className="w-10 h-10 rounded-xl flex flex-shrink-0 items-center justify-center bg-white/[0.03] border border-white/[0.05] text-neutral-400 group-hover:text-neutral-200 transition-colors">
                {option.icon}
            </div>
            <div>
                <h3 className="text-neutral-200 font-medium font-mono text-[13px] tracking-tight">{option.title}</h3>
                <p className="text-neutral-500 text-[12px] mt-1.5 leading-relaxed">{option.description}</p>
            </div>
        </div>
        <div className="flex items-center gap-2 pt-2 border-t border-white/[0.05]">
            <button
                onClick={() => onExport(option.endpoint, option.filename)}
                disabled={exporting}
                className="flex-1 py-2 bg-white/5 hover:bg-white/10 text-neutral-300 rounded-xl text-[12px] font-medium transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
            >
                <Download className="w-3.5 h-3.5" />
                {exporting ? 'Génération…' : 'Télécharger'}
            </button>
            <button
                onClick={() => onReadme(option)}
                className="p-2 bg-transparent hover:bg-white/5 text-neutral-500 hover:text-neutral-300 rounded-xl transition-colors flex items-center justify-center border border-transparent hover:border-white/[0.05]"
                title="Consulter le README"
            >
                <FileText className="w-4 h-4" />
            </button>
        </div>
    </div>
);

interface SectionHeaderProps {
    icon: React.ReactNode;
    title: string;
    description: string;
}

const SectionHeader: React.FC<SectionHeaderProps> = ({ icon, title, description }) => (
    <div>
        <h2 className="text-xl font-medium tracking-tight text-neutral-100 flex items-center gap-2.5">
            {icon}
            {title}
        </h2>
        <p className="text-neutral-400 mt-1.5 text-sm leading-relaxed max-w-2xl">{description}</p>
    </div>
);

export const ExportStudio: React.FC = () => {
    const [exportingState, setExportingState] = useState<Record<string, boolean>>({});
    const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
    
    // ML Status
    const [mlStatus, setMlStatus] = useState<{ status: string; active_model: string; model_type: string; nodes_loaded: number; expected_features?: number } | null>(null);
    const [isSyncing, setIsSyncing] = useState(false);
    
    // ML Test
    const [testSourceUri, setTestSourceUri] = useState<string>("http://nsxai.org/Patient/P_42");
    const [testRecommendations, setTestRecommendations] = useState<any[] | null>(null);
    const [isTesting, setIsTesting] = useState(false);
    
    // ML Training Results
    const [trainingResults, setTrainingResults] = useState<any[]>([]);

    const aggregatedResults = useMemo(() => {
        if (!trainingResults || trainingResults.length === 0) return [];
        const map = new Map();
        for (const r of trainingResults) {
            if (!r.model || r.model === "LR CrossVal") continue;
            if (!map.has(r.model)) map.set(r.model, { roc: [], ap: [], f1: [] });
            map.get(r.model).roc.push(r.roc_auc || 0);
            map.get(r.model).ap.push(r.average_precision || 0);
            map.get(r.model).f1.push(r.f1 || 0);
        }
        const agg = Array.from(map.entries()).map(([model, data]: any) => {
            const mean = (arr: number[]) => arr.reduce((a,b)=>a+b,0)/Math.max(1, arr.length);
            return {
                model,
                roc: mean(data.roc),
                ap: mean(data.ap),
                f1: mean(data.f1)
            };
        });
        return agg.sort((a,b) => b.roc - a.roc);
    }, [trainingResults]);

    const fetchMlStatus = async () => {
        try {
            const res = await fetchApi('/api/predict/status');
            if (res.ok) {
                const data = await res.json();
                setMlStatus(data);
            }
        } catch (e) {
            console.error("Failed to fetch ML status", e);
        }
    };
    
    const fetchTrainingResults = async () => {
        try {
            const res = await fetchApi('/api/predict/training-results');
            if (res.ok) {
                const data = await res.json();
                if (data.status === 'ok') {
                    setTrainingResults(data.data);
                }
            }
        } catch (e) {
            console.error("Failed to fetch training results", e);
        }
    };

    useEffect(() => {
        fetchMlStatus();
        fetchTrainingResults();
    }, []);

    const modelFileNameMap: Record<string, string> = {
        "GCN": "GCN_LP.pt",
        "GraphSAGE": "GraphSAGE_LP.pt",
        "MLP": "MLP_LP.pt",
        "Random Forest": "Random_Forest.pkl",
        "XGBoost": "XGBoost.json"
    };

    const handleActivateModel = async (modelName: string) => {
        const filename = modelFileNameMap[modelName];
        if (!filename) return;
        
        setMessage(null);
        try {
            const res = await fetchApi('/api/predict/select-model', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model_name: filename })
            });
            const data = await res.json();
            if (res.ok) {
                setMessage({ type: 'success', text: `Modèle ${filename} activé avec succès.` });
                fetchMlStatus();
            } else {
                throw new Error(data.detail || "Erreur d'activation");
            }
        } catch (e: any) {
            setMessage({ type: 'error', text: e.message });
        }
    };

    const handleExport = async (endpoint: string, filename: string) => {
        setExportingState(prev => ({ ...prev, [filename]: true }));
        setMessage(null);
        try {
            const res = await fetchApi(endpoint);
            if (!res.ok) throw new Error(`Erreur lors de l'export de ${filename}`);
            const blob = await res.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            setMessage({ type: 'success', text: `Fichier ${filename} téléchargé avec succès.` });
        } catch (e: any) {
            setMessage({ type: 'error', text: e.message });
        } finally {
            setExportingState(prev => ({ ...prev, [filename]: false }));
        }
    };

    const handleSyncGraph = async () => {
        setIsSyncing(true);
        setMessage(null);
        try {
            await fetchApi('/api/predict/sync', { method: 'POST' });
            setMessage({ type: 'success', text: "Synchronisation du graphe lancée en arrière-plan." });
            setTimeout(fetchMlStatus, 2000);
        } catch (e: any) {
            setMessage({ type: 'error', text: "Erreur lors du lancement de la synchro." });
        } finally {
            setIsSyncing(false);
        }
    };

    const handleTestModel = async () => {
        if (!testSourceUri) return;
        setIsTesting(true);
        setTestRecommendations(null);
        try {
            const res = await fetchApi('/api/predict/recommendations', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source_uri: testSourceUri, top_k: 5 })
            });
            const data = await res.json();
            if (res.ok) {
                setTestRecommendations(data.recommendations);
            } else {
                setMessage({ type: 'error', text: data.detail || "Erreur de prédiction" });
            }
        } catch (e: any) {
            setMessage({ type: 'error', text: e.message });
        } finally {
            setIsTesting(false);
        }
    };

    const handleReadmeDownload = (option: any) => {
        const blob = new Blob([option.readme], { type: 'text/plain;charset=utf-8' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `README_${option.filename}.txt`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
    };

    // ── Sections ──────────────────────────────────────────────────────────────

    const ML_EXPORTS = [
        {
            title: "triples.tsv",
            description: "Triplets symboliques (labels courts) dédupliqués. Point d'entrée pour explorer le KG avant encodage.",
            endpoint: "/api/export/ml/triples.tsv",
            filename: "triples.tsv",
            icon: <Database className="w-5 h-5 text-orange-400" />,
            color: "orange",
            readme: `=== README : triples.tsv ===
Format : TSV (Tab Separated Values)

COLONNES :
1. head  – label court de l'entité source
2. rel   – label court de la relation
3. tail  – label court de l'entité cible

USAGE :
Exploration humaine du graphe, vérification qualité, première étape avant encodage numérique.
Compatible : pd.read_csv(f, sep='\\t')

OUTILS : Pandas, PyKEEN, AmpliGraph`,
        },
        {
            title: "triples_encoded.tsv",
            description: "Triplets encodés en indices entiers (head_id, rel_id, tail_id). Prêt pour PyKEEN, DGL-KE, RotatE.",
            endpoint: "/api/export/ml/triples_encoded.tsv",
            filename: "triples_encoded.tsv",
            icon: <Activity className="w-5 h-5 text-rose-400" />,
            color: "rose",
            readme: `=== README : triples_encoded.tsv ===
Format : TSV (Tab Separated Values)

COLONNES :
1. head_id  – indice entier de l'entité source
2. rel_id   – indice entier de la relation
3. tail_id  – indice entier de l'entité cible

USAGE :
Injection directe dans PyTorch DataLoader ou DGL-KE.
Utiliser mapping.json pour décoder les indices.

OUTILS : PyKEEN, DGL-KE, LibKGE, AmpliGraph`,
        },
        {
            title: "entities.tsv",
            description: "Features par entité : type, degrés, hub_score, authority_score. Features initiales pour GNN.",
            endpoint: "/api/export/ml/entities.tsv",
            filename: "entities.tsv",
            icon: <Layers className="w-5 h-5 text-sky-400" />,
            color: "sky",
            readme: `=== README : entities.tsv ===
Format : TSV (Tab Separated Values)

COLONNES :
1. id             – indice entier (correspond à triples_encoded.tsv)
2. label          – nom lisible
3. primary_type   – premier type RDF
4. type_count     – nombre de types déclarés
5. out_degree     – nombre de relations sortantes
6. in_degree      – nombre de relations entrantes
7. total_degree   – somme des deux
8. hub_score      – out / total  → proche de 1 = source/catégorie parente
9. authority_score– in / total   → proche de 1 = feuille/concept cible
10. comment       – rdfs:comment si disponible

USAGE :
Features initiales des nœuds pour R-GCN, GraphSAGE, GAT.
Segmentation et filtrage avant entraînement.`,
        },
        {
            title: "relations.tsv",
            description: "Métadonnées sémantiques des relations : usage, domaine, range, flags OWL (symétrique, transitif…).",
            endpoint: "/api/export/ml/relations.tsv",
            filename: "relations.tsv",
            icon: <GitBranch className="w-5 h-5 text-violet-400" />,
            color: "violet",
            readme: `=== README : relations.tsv ===
Format : TSV (Tab Separated Values)

COLONNES :
1. id          – indice entier de la relation
2. label       – nom lisible
3. usage       – nombre de triplets utilisant cette relation
4. domains     – types de sujets attendus (séparés par virgule)
5. ranges      – types d'objets attendus
6. symmetric   – 1 si owl:SymmetricProperty
7. transitive  – 1 si owl:TransitiveProperty
8. functional  – 1 si owl:FunctionalProperty

USAGE :
Pondération des relations dans TransE/RotatE/ComplEx.
Contraintes de type pour filtrer les négatifs mal formés.`,
        },
        {
            title: "paths2.tsv",
            description: "Chemins de longueur 2 (s→mid→o). Contexte de voisinage pour GNN, PRA, AMIE.",
            endpoint: "/api/export/ml/paths2.tsv",
            filename: "paths2.tsv",
            icon: <Share2 className="w-5 h-5 text-teal-400" />,
            color: "teal",
            readme: `=== README : paths2.tsv ===
Format : TSV (Tab Separated Values)

COLONNES :
1. head_id  – entité source
2. rel1_id  – première relation
3. mid_id   – entité intermédiaire
4. rel2_id  – deuxième relation
5. tail_id  – entité cible

USAGE :
Génération de règles d'inférence (AMIE, PRA).
Features de chemin pour R-GCN, TransE-path.
Détection de relations implicites (link prediction par chemin).`,
        },
        {
            title: "literals.tsv",
            description: "Attributs littéraux (texte, nombres, dates) par entité. Features textuelles/numériques pour modèles hybrides.",
            endpoint: "/api/export/ml/literals.tsv",
            filename: "literals.tsv",
            icon: <AlignLeft className="w-5 h-5 text-amber-400" />,
            color: "amber",
            readme: `=== README : literals.tsv ===
Format : TSV (Tab Separated Values)

COLONNES :
1. entity_id    – indice entier de l'entité
2. predicate_id – indice entier du prédicat
3. value        – valeur brute (string, nombre, date…)
4. datatype     – type XSD court (string, integer, date, float…)

USAGE :
Features initiales textuelles ou numériques pour modèles KGE + attributs (EARL, KG-BERT).
Encodage BERT des labels/commentaires pour initialisation d'embeddings.`,
        },
        {
            title: "negatives.tsv",
            description: "Triplets positifs + négatifs CWA avec colonne label et corrupt_side. Prêt pour l'entraînement.",
            endpoint: "/api/export/ml/negatives.tsv",
            filename: "negatives.tsv",
            icon: <BrainCircuit className="w-5 h-5 text-pink-400" />,
            color: "pink",
            readme: `=== README : negatives.tsv ===
Format : TSV (Tab Separated Values)

COLONNES :
1. head_id       – indice entité source
2. rel_id        – indice relation
3. tail_id       – indice entité cible
4. label         – 1 = triplet réel | 0 = négatif généré
5. corrupt_side  – h = tête corrompue | t = queue corrompue | - = positif

USAGE :
Entraînement discriminatif : link prediction, classification de triplets.
corrupt_side permet d'entraîner des modèles asymétriques ou d'analyser les erreurs.

Options disponibles via query string :
  ?seed=42          – reproductibilité
  ?neg_ratio=2      – 2 négatifs par positif (défaut : 1)
  ?strategy=both    – head | tail | both`,
        },
    ];

    const REFERENCE_EXPORTS = [
        {
            title: "mapping.json",
            description: "Dictionnaires id↔URI↔label pour entités et relations, avec degrés. Référence obligatoire pour décoder les TSV.",
            endpoint: "/api/export/ml/mapping.json",
            filename: "mapping.json",
            icon: <FileJson className="w-5 h-5 text-yellow-400" />,
            color: "yellow",
            readme: `=== README : mapping.json ===
Format : JSON

STRUCTURE :
{
  "meta": { generated_at, num_entities, num_relations, num_triples },
  "entities":  { "<id>": { uri, label, types, out_degree, in_degree } },
  "relations": { "<id>": { uri, label, usage, symmetric, transitive, functional } }
}

USAGE :
Décoder les indices entiers des fichiers .tsv en URIs/labels lisibles.
Charger dans PyTorch comme lookup table d'embeddings.`,
        },
        {
            title: "stats.json",
            description: "Métriques descriptives : densité, degrés (médiane, P95), couverture des types, fréquence des relations.",
            endpoint: "/api/export/ml/stats.json",
            filename: "stats.json",
            icon: <BarChart2 className="w-5 h-5 text-lime-400" />,
            color: "lime",
            readme: `=== README : stats.json ===
Format : JSON

SECTIONS :
- graph          : num_entities, num_relations, num_triples, density
- degrees        : avg, median, p95, max_out, max_in
- coverage       : entités typées, entités labellisées (%)
- relation_frequency : classement par usage décroissant
- type_distribution  : nombre d'entités par type

USAGE :
Vérification qualité avant entraînement.
Détection de déséquilibres (classes rares, relations dominantes).`,
        },
        {
            title: "type_cooccurrence.json",
            description: "Membres par type RDF. Base des paires positives pour l'apprentissage contrastif.",
            endpoint: "/api/export/ml/type_cooccurrence.json",
            filename: "type_cooccurrence.json",
            icon: <FileJson className="w-5 h-5 text-cyan-400" />,
            color: "cyan",
            readme: `=== README : type_cooccurrence.json ===
Format : JSON

STRUCTURE :
{
  "types": {
    "<type_label>": { uri, count, members: ["label1", "label2", ...] }
  }
}

USAGE :
Construire des paires positives (même type → similarité structurelle)
et des paires négatives (types distincts) pour l'apprentissage contrastif (SimCLE, GraphCL).
Stratification des splits train/val/test par type.`,
        },
    ];

    const GRAPH_EXPORTS = [
        {
            title: "nodes.csv",
            description: "Nœuds enrichis avec types, degrés, hub_score et authority_score. Compatible Gephi / NetworkX.",
            endpoint: "/api/export/nodes.csv",
            filename: "nodes.csv",
            icon: <FileSpreadsheet className="w-5 h-5 text-blue-400" />,
            color: "blue",
            readme: `=== README : nodes.csv ===
Format : CSV

COLONNES : id, label, primary_type, type_count, out_degree, in_degree, hub_score, authority_score
OUTILS : Gephi, Neo4j, NetworkX, Cytoscape`,
        },
        {
            title: "edges.csv",
            description: "Arêtes avec poids normalisé (usage relatif de la relation), flags symétrique/transitif.",
            endpoint: "/api/export/edges.csv",
            filename: "edges.csv",
            icon: <Share2 className="w-5 h-5 text-indigo-400" />,
            color: "indigo",
            readme: `=== README : edges.csv ===
Format : CSV

COLONNES : source, target, relation, weight (usage normalisé 0-1), symmetric, transitive
OUTILS : Gephi, Neo4j, NetworkX, Cytoscape`,
        },
        {
            title: "graph.graphml",
            description: "GraphML avec attributs sémantiques complets sur nœuds et arêtes. Compatible Gephi, yEd, igraph.",
            endpoint: "/api/export/graphml",
            filename: "graph.graphml",
            icon: <Share2 className="w-5 h-5 text-purple-400" />,
            color: "purple",
            readme: `=== README : graph.graphml ===
Format : GraphML (XML)

Attributs nœuds : label, primary_type, out_degree, in_degree, hub_score
Attributs arêtes : label, usage, symmetric
OUTILS : Gephi, yEd, NetworkX (read_graphml), igraph`,
        },
    ];



    return (
        <div className="h-full flex flex-col p-8 border border-white/10 bg-[#0a0a0a]/80 backdrop-blur-2xl rounded-[2rem] shadow-2xl ring-1 ring-white/5 overflow-y-auto custom-scrollbar animate-in fade-in duration-500">
            <div className="max-w-4xl mx-auto w-full space-y-10">

                {message && (
                    <div className={`p-3.5 rounded-xl border text-sm flex items-start gap-2.5 ${message.type === 'success' ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' : 'bg-red-500/10 border-red-500/20 text-red-400'}`}>
                        {message.type === 'success' ? <CheckCircle2 className="w-4 h-4 flex-shrink-0 mt-0.5" /> : <span className="font-bold flex-shrink-0">!</span>}
                        {message.text}
                    </div>
                )}

                {/* ── ML Exports ── */}
                <section className="space-y-4">
                    <SectionHeader
                        icon={<BrainCircuit className="w-5 h-5 text-neutral-500" />}
                        title="Exports ML — Entraînement"
                        description="Fichiers TSV optimisés pour les modèles KGE (TransE, RotatE, ComplEx), GNN (R-GCN, GraphSAGE) et l'apprentissage contrastif."
                    />
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        {ML_EXPORTS.map(o => <ExportCard key={o.filename} option={o} exporting={!!exportingState[o.filename]} onExport={handleExport} onReadme={handleReadmeDownload} />)}
                    </div>
                </section>

                {/* ── Reference files ── */}
                <section className="space-y-4 pt-6 border-t border-neutral-800/40">
                    <SectionHeader
                        icon={<FileJson className="w-5 h-5 text-neutral-500" />}
                        title="Référence & Statistiques"
                        description="Métadonnées indispensables pour décoder les indices, vérifier la qualité du graphe et construire des splits d'entraînement équilibrés."
                    />
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        {REFERENCE_EXPORTS.map(o => <ExportCard key={o.filename} option={o} exporting={!!exportingState[o.filename]} onExport={handleExport} onReadme={handleReadmeDownload} />)}
                    </div>
                </section>

                {/* ── Graph Exports ── */}
                <section className="space-y-4 pt-6 border-t border-neutral-800/40">
                    <SectionHeader
                        icon={<Share2 className="w-5 h-5 text-neutral-500" />}
                        title="Exports Graphe — Visualisation"
                        description="Formats pour Gephi, NetworkX et Neo4j. Nœuds et arêtes enrichis avec degrés, types et poids sémantiques."
                    />
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        {GRAPH_EXPORTS.map(o => <ExportCard key={o.filename} option={o} exporting={!!exportingState[o.filename]} onExport={handleExport} onReadme={handleReadmeDownload} />)}
                    </div>
                </section>

                {/* ── Test Model (Replacing Status) ── */}
                <section className="space-y-4 pt-6 border-t border-neutral-800/40">
                    <SectionHeader
                        icon={<BrainCircuit className="w-5 h-5 text-neutral-500" />}
                        title="Tester le Modèle Actif"
                        description={`Vérifiez concrètement les prédictions du modèle en temps réel. Modèle actuel : ${mlStatus?.active_model || 'Aucun'} ${mlStatus?.expected_features ? `(${mlStatus.expected_features} features attendues)` : ''}`}
                    />
                    <div className="bg-white/[0.02] p-6 rounded-2xl border border-white/[0.05] space-y-4">
                        <div className="flex gap-3">
                            <input
                                type="text"
                                value={testSourceUri}
                                onChange={(e) => setTestSourceUri(e.target.value)}
                                placeholder="URI du nœud (ex: http://nsxai.org/Patient/P_42)"
                                className="flex-1 bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-neutral-200 outline-none focus:border-emerald-500/50 transition-colors"
                            />
                            <button
                                onClick={handleTestModel}
                                disabled={isTesting || mlStatus?.status !== 'ready'}
                                className="px-6 py-2.5 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/20 rounded-xl text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {isTesting ? 'Calcul...' : 'Prédire'}
                            </button>
                        </div>
                        
                        {testRecommendations && (
                            <div className="mt-4 space-y-2">
                                <h4 className="text-xs font-medium text-neutral-400 uppercase tracking-wider mb-3">Top 5 Liens Suggérés</h4>
                                {testRecommendations.length === 0 ? (
                                    <p className="text-sm text-neutral-500">Aucune recommandation trouvée.</p>
                                ) : (
                                    <div className="grid grid-cols-1 gap-2">
                                        {testRecommendations.map((r: any, idx: number) => (
                                            <div key={idx} className="flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/5">
                                                <span className="text-sm text-neutral-300 font-mono truncate">{r.target_uri}</span>
                                                <span className="text-xs font-medium text-emerald-400 bg-emerald-500/10 px-2.5 py-1 rounded-lg">
                                                    {(r.probability * 100).toFixed(1)}%
                                                </span>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </section>
                
                {/* ── Training Results Leaderboard ── */}
                {aggregatedResults.length > 0 && (
                    <section className="space-y-4 pt-6 border-t border-neutral-800/40">
                        <SectionHeader
                            icon={<BarChart2 className="w-5 h-5 text-neutral-500" />}
                            title="Résultats d'Entraînement ML (Colab)"
                            description="Performances moyennes (ROC-AUC) des modèles entraînés sur vos données."
                        />
                        <div className="bg-white/[0.02] p-5 rounded-2xl border border-white/[0.05] overflow-x-auto">
                            <table className="w-full text-sm text-left">
                                <thead className="text-xs text-neutral-400 uppercase bg-white/[0.02]">
                                    <tr>
                                        <th className="px-4 py-3 font-medium">Modèle</th>
                                        <th className="px-4 py-3 font-medium">ROC-AUC</th>
                                        <th className="px-4 py-3 font-medium">Avg Precision</th>
                                        <th className="px-4 py-3 font-medium">F1 Score</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {aggregatedResults.map((res, i) => {
                                        const filename = modelFileNameMap[res.model];
                                        const isActive = mlStatus?.active_model === filename;
                                        return (
                                        <tr key={res.model} className="border-b border-white/[0.05] last:border-0 hover:bg-white/[0.02]">
                                            <td className="px-4 py-3 font-medium text-neutral-200 flex items-center gap-2">
                                                {i === 0 && <span className="w-2 h-2 rounded-full bg-emerald-500" title="Meilleur modèle" />}
                                                {res.model}
                                            </td>
                                            <td className="px-4 py-3 text-neutral-300 font-mono">{(res.roc * 100).toFixed(1)}%</td>
                                            <td className="px-4 py-3 text-neutral-400 font-mono">{(res.ap * 100).toFixed(1)}%</td>
                                            <td className="px-4 py-3 text-neutral-400 font-mono">{(res.f1 * 100).toFixed(1)}%</td>
                                            <td className="px-4 py-3 text-right">
                                                {filename ? (
                                                    <button
                                                        onClick={() => handleActivateModel(res.model)}
                                                        disabled={isActive}
                                                        className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                                                            isActive 
                                                                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 cursor-default' 
                                                                : 'bg-white/5 hover:bg-white/10 text-neutral-300 border border-white/5 hover:border-white/10'
                                                        }`}
                                                    >
                                                        {isActive ? 'Actif' : 'Activer'}
                                                    </button>
                                                ) : (
                                                    <span className="text-xs text-neutral-600">Non exporté</span>
                                                )}
                                            </td>
                                        </tr>
                                    )})}
                                </tbody>
                            </table>
                        </div>
                    </section>
                )}
            </div>
        </div>
    );
};