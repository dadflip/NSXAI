import React, { useEffect, useState } from 'react';
import { Layers, Database, Braces, ArrowRight, BrainCircuit, Activity, Cpu, Sparkles, Import, ShieldCheck } from 'lucide-react';
import { apiUrl } from '../lib/api';

export const PipelineStudio: React.FC = () => {
    const [reasonerStats, setReasonerStats] = useState<any>(null);

    useEffect(() => {
        fetch(apiUrl('/api/reasoner/stats'))
            .then(r => r.json())
            .then(d => setReasonerStats(d))
            .catch(console.error);
    }, []);

    return (
        <div className="max-w-4xl mx-auto py-8 space-y-12 animate-in fade-in duration-500">
            <section className="space-y-4">
                <div className="flex items-center gap-3">
                    <Layers className="w-6 h-6 text-neutral-500" />
                    <h2 className="text-2xl font-medium tracking-tight text-neutral-100">Le Pipeline ELT (Extract, Load, Transform)</h2>
                </div>
                <p className="text-neutral-400 leading-relaxed text-[15px]">
                    Contrairement à un ETL classique (où la donnée est transformée <em>avant</em> son insertion), ce moteur repose sur un paradigme <strong>ELT orienté Graphe</strong>. 
                    L'ontologie OWL brute est extraite, immédiatement chargée dans un Triplestore (Oxigraph), et c'est au sein de cette base de graphe que s'opèrent les transformations complexes (Inférence et Raisonnement).
                </p>
            </section>

            <div className="relative">
                {/* Ligne connectrice */}
                <div className="absolute top-0 bottom-0 left-8 md:left-[2.25rem] w-px bg-gradient-to-b from-indigo-500 via-emerald-500 to-purple-500 opacity-20"></div>

                <div className="space-y-12 relative">
                    
                    {/* E - Extract */}
                    <div className="flex flex-col md:flex-row gap-6 items-start">
                        <div className="flex-shrink-0 w-16 h-16 rounded-2xl bg-neutral-900 border border-neutral-800 flex items-center justify-center relative z-10 shadow-xl shadow-black/50">
                            <Braces className="w-6 h-6 text-indigo-400" />
                        </div>
                        <div className="pt-2 flex-grow space-y-4 max-w-2xl">
                            <div className="flex items-center gap-2">
                                <span className="text-indigo-400 font-mono font-bold text-lg">E</span>
                                <h3 className="text-xl font-medium text-neutral-200">Extract (Extraction & Parsing)</h3>
                            </div>
                            <p className="text-neutral-400 text-sm leading-relaxed">
                                Le moteur parcourt les fichiers sources (ex: <code>gato.owl</code>), parse la syntaxe XML/OWL grâce à notre parser customisé (ou <code>fast-xml-parser</code>) pour résoudre les URIs et traduire la structure en triplets standards W3C (Sujet, Prédicat, Objet).
                            </p>
                            <div className="bg-neutral-900/50 rounded-xl p-4 border border-indigo-500/10 space-y-3">
                                <div className="flex items-center gap-3 text-sm text-neutral-300">
                                    <Import className="w-4 h-4 text-indigo-500" />
                                    <span>Détection automatique et résolution des directives <code>owl:imports</code></span>
                                </div>
                                <div className="flex items-center gap-3 text-sm text-neutral-300">
                                    <Activity className="w-4 h-4 text-indigo-500" />
                                    <span>Conversion à la volée du XML vers N-Triples</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* L - Load */}
                    <div className="flex flex-col md:flex-row gap-6 items-start">
                        <div className="flex-shrink-0 w-16 h-16 rounded-2xl bg-neutral-900 border border-neutral-800 flex items-center justify-center relative z-10 shadow-xl shadow-black/50">
                            <Database className="w-6 h-6 text-emerald-400" />
                        </div>
                        <div className="pt-2 flex-grow space-y-4 max-w-2xl">
                            <div className="flex items-center gap-2">
                                <span className="text-emerald-400 font-mono font-bold text-lg">L</span>
                                <h3 className="text-xl font-medium text-neutral-200">Load (Chargement brut)</h3>
                            </div>
                            <p className="text-neutral-400 text-sm leading-relaxed">
                                Au lieu de manipuler de vastes structures JSON ou objets en mémoire, chaque liasse de triplets est directement insérée dans <strong>Oxigraph</strong>, un Triplestore embarqué (écrit en Rust), optimisé pour les hautes performances.
                            </p>
                            <div className="bg-neutral-900/50 rounded-xl p-4 border border-emerald-500/10 space-y-3">
                                <div className="flex items-center gap-3 text-sm text-neutral-300">
                                    <Cpu className="w-4 h-4 text-emerald-500" />
                                    <span>Insertion massive (Bulk Load) dans le store en-mémoire</span>
                                </div>
                                <div className="flex items-center gap-3 text-sm text-neutral-300">
                                    <Database className="w-4 h-4 text-emerald-500" />
                                    <span>Indexation immédiate pour des requêtes SPARQL instantanées</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* T - Transform */}
                    <div className="flex flex-col md:flex-row gap-6 items-start">
                        <div className="flex-shrink-0 w-16 h-16 rounded-2xl bg-neutral-900 border border-neutral-800 flex items-center justify-center relative z-10 shadow-xl shadow-black/50">
                            <BrainCircuit className="w-6 h-6 text-purple-400" />
                        </div>
                        <div className="pt-2 flex-grow space-y-4 max-w-2xl">
                            <div className="flex items-center gap-2">
                                <span className="text-purple-400 font-mono font-bold text-lg">T</span>
                                <h3 className="text-xl font-medium text-neutral-200">Transform (Raisonnement & Inférence)</h3>
                            </div>
                            <p className="text-neutral-400 text-sm leading-relaxed">
                                C'est au sein du Triplestore que la véritable magie opère. Le système exécute une série de règles d'inférence (via des requêtes <em>SPARQL UPDATE</em>) pour générer, en direct, de nouvelles connaissances implicites qui n'étaient pas explicitées dans les fichiers d'origine.
                            </p>
                            <div className="bg-neutral-900/50 rounded-xl p-4 border border-purple-500/10 space-y-3">
                                <div className="flex items-center gap-3 text-sm text-neutral-300">
                                    <ArrowRight className="w-4 h-4 text-purple-500" />
                                    <span><strong>Transitivité :</strong> Déduit la hiérarchie parente à N niveaux (ex: <em>a sous-classe de b, b sous-classe de c = a sous-classe de c</em>)</span>
                                </div>
                                <div className="flex items-center gap-3 text-sm text-neutral-300">
                                    <Sparkles className="w-4 h-4 text-purple-500" />
                                    <span><strong>Typage automatique :</strong> Assigne automatiquement la classe parent via <code>rdfs:subClassOf</code></span>
                                </div>
                                <div className="flex items-center gap-3 text-sm text-neutral-300">
                                    <BrainCircuit className="w-4 h-4 text-purple-500" />
                                    <span>Résolution des Domaines (<code>rdfs:domain</code>) et Ranges (<code>rdfs:range</code>) directement en base</span>
                                </div>
                            </div>
                            
                            {/* Live Stats */}
                            {reasonerStats && (
                                <div className="mt-6 border border-emerald-500/30 bg-emerald-500/10 p-4 rounded-xl">
                                    <div className="flex items-center gap-2 mb-2">
                                        <Sparkles className="w-4 h-4 text-emerald-400" />
                                        <h4 className="text-emerald-300 font-medium text-sm">Feedback du Raisonneur en Direct</h4>
                                    </div>
                                    <div className="grid grid-cols-2 gap-4 mt-3">
                                        <div className="bg-neutral-900/50 p-3 rounded-lg border border-emerald-500/10">
                                            <p className="text-neutral-400 text-xs uppercase tracking-wider mb-1">Cerveau Triplestore</p>
                                            <p className="text-xl font-mono text-emerald-100">{reasonerStats.totalTriples.toLocaleString()} <span className="text-xs text-neutral-500 font-sans">triplets totaux</span></p>
                                        </div>
                                        <div className="bg-neutral-900/50 p-3 rounded-lg border border-emerald-500/10">
                                            <p className="text-neutral-400 text-xs uppercase tracking-wider mb-1">Connaissances Déduites</p>
                                            <p className="text-xl font-mono text-emerald-300">+{reasonerStats.inferredTriples.toLocaleString()} <span className="text-xs text-neutral-500 font-sans">nouvelles inférences</span></p>
                                        </div>
                                    </div>
                                    
                                    <div className="mt-4 pt-3 border-t border-emerald-500/20">
                                        <p className="text-xs text-emerald-400/80 mb-2 font-medium">Contraintes SHACL & Règles (Embarquées)</p>
                                        <ul className="text-xs text-emerald-200/60 space-y-1 font-mono">
                                           {reasonerStats.rules.map((r: string, idx: number) => (
                                              <li key={idx}>- {r}</li>
                                           ))}
                                           <li>- Contraintes SHACL (WIP : Not yet strict enforcing interface, log basis only).</li>
                                        </ul>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>

                </div>
            </div>
            
            <div className="bg-neutral-900/60 border border-neutral-800/70 p-6 rounded-2xl">
                 <h4 className="text-neutral-100 font-medium mb-3">Pourquoi cette architecture ?</h4>
                 <p className="text-neutral-400 text-sm leading-relaxed">
                    Le modèle "Transform en dernier" (ELT) s'adapte parfaitement aux modèles sémantiques. 
                    Il est très complexe d'inférer des graphes par script impératif durant l'extraction. En chargeant d'abord 
                    les données brutes dans le moteur de graphe, nous exploitons la puissance mathématique de SPARQL pour appliquer 
                    les transformations (raisonnement OWL/RDFS) sur la totalité du graphe fusionné. 
                    Le résultat final, riche et implicitement connecté, est alors prêt à être exporté.
                 </p>
            </div>
        </div>
    );
};
