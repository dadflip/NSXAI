"""
Ontology Loader using owlready2
Supports formats: OWL, RDF/XML, Turtle.
"""

from pathlib import Path
from typing import Dict, Optional
import json
import datetime
from owlready2 import get_ontology, set_log_level, onto_path

set_log_level(1)

_EXTENSIONS = [".owl", ".rdf", ".ttl"]

# Dépendances distantes → fichiers locaux, ordre important (feuilles en premier)
_DEPENDENCIES = [
    ("http://surveys.nees.com.br/ontologies/its/its.domain.owl",      "itsdomain.owl"),
    ("http://surveys.nees.com.br/ontologies/its/its.pedagogical.owl", "its.pedagogical.owl"),
]

# Ontologies par défaut
DEFAULT_ONTOLOGIES = {
    "gato":           "gato.owl",
    "gado_core":      "gado_core.owl",
    "gado_full":      "gado_full.owl",
    "its.pedagogical": "its.pedagogical.owl",
    "itsdomain":      "itsdomain.owl",
}

# ─── Wrapper ──────────────────────────────────────────────────────────────────

class OntologyGraph:
    """Wrapper owlready2 avec support de len()."""

    def __init__(self, ontology):
        self._ontology = ontology

    def __len__(self):
        return sum(1 for _ in self._ontology.get_triples())

    def __getattr__(self, name):
        return getattr(self._ontology, name)


# ─── Loader ───────────────────────────────────────────────────────────────────

class OntologyLoader:
    """Charge et gère des ontologies OWL depuis un dossier local."""

    def __init__(self, ontologies_dir: Optional[Path] = None):
        if ontologies_dir is None:
            self.ontologies_dir = (
                Path(__file__).parent.parent.parent.parent.parent / "public" / "ontologies"
            )
        else:
            self.ontologies_dir = Path(ontologies_dir)

        self.loaded_graphs: Dict[str, OntologyGraph] = {}

        if str(self.ontologies_dir) not in onto_path:
            onto_path.append(str(self.ontologies_dir))

        self._preload_dependencies()

    def _preload_dependencies(self):
        """Enregistrer les IRIs distantes vers leurs fichiers locaux
        avant tout chargement, dans l'ordre de dépendance."""
        import owlready2
        for iri, filename in _DEPENDENCIES:
            local = self.ontologies_dir / filename
            if local.exists() and iri not in owlready2.default_world.ontologies:
                onto = get_ontology(iri)
                onto.load(fileobj=open(local, "rb"), only_local=True)

    def load_ontology(self, name: str) -> OntologyGraph:
        """Charger une ontologie par nom (sans extension)."""
        for ext in _EXTENSIONS:
            filepath = self.ontologies_dir / f"{name}{ext}"
            if filepath.exists():
                ontology = get_ontology(str(filepath.resolve()))
                try:
                    ontology.load(only_local=True)
                except Exception:
                    try:
                        ontology.load()
                    except Exception as err:
                        raise RuntimeError(f"Impossible de charger '{name}': {err}") from err

                graph = OntologyGraph(ontology)
                self.loaded_graphs[name] = graph
                return graph

        raise FileNotFoundError(f"Ontologie '{name}' introuvable dans {self.ontologies_dir}")

    def get_statistics(self, name: str) -> Dict:
        """Statistiques d'une ontologie chargée."""
        if name not in self.loaded_graphs:
            raise ValueError(f"Ontologie '{name}' non chargée.")
        graph = self.loaded_graphs[name]
        onto = graph._ontology
        return {
            "name":        name,
            "triples":     len(graph),
            "classes":     len(list(onto.classes())),
            "properties":  len(list(onto.properties())),
            "individuals": len(list(onto.individuals())),
        }

    def list_loaded(self) -> list:
        return list(self.loaded_graphs.keys())

    def generate_simple_report(self, output_path: str) -> Path:
        """Générer un rapport texte simple."""
        lines = []
        lines.append("=" * 60)
        lines.append("RAPPORT DES ONTOLOGIES")
        lines.append("=" * 60)
        lines.append(f"Dossier: {self.ontologies_dir}")
        lines.append(f"Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Ontologies chargées: {len(self.loaded_graphs)}")
        lines.append("")
        
        total_triples = 0
        total_classes = 0
        total_properties = 0
        total_individuals = 0
        
        for name in sorted(self.loaded_graphs.keys()):
            graph = self.loaded_graphs[name]
            onto = graph._ontology
            stats = self.get_statistics(name)
            
            total_triples += stats['triples']
            total_classes += stats['classes']
            total_properties += stats['properties']
            total_individuals += stats['individuals']
            
            lines.append(f"{'─' * 40}")
            lines.append(f"{name.upper()}")
            lines.append(f"{'─' * 40}")
            lines.append(f"  Triples:     {stats['triples']}")
            lines.append(f"  Classes:     {stats['classes']}")
            lines.append(f"  Propriétés:  {stats['properties']}")
            lines.append(f"  Individus:   {stats['individuals']}")
            lines.append("")
            
            # Classes complètes
            classes = list(onto.classes())
            if classes:
                lines.append("  Classes:")
                for cls in sorted(classes, key=lambda c: c.name):
                    parents = [p.name for p in cls.is_a if hasattr(p, "name") and p.name != "Thing"]
                    if parents:
                        lines.append(f"    • {cls.name} (hérite de: {', '.join(parents)})")
                    else:
                        lines.append(f"    • {cls.name}")
                lines.append("")
            
            # Propriétés complètes
            props = list(onto.properties())
            if props:
                obj_props = [p for p in props if hasattr(p, 'is_a') and any('ObjectProperty' in str(a) for a in p.is_a)]
                data_props = [p for p in props if hasattr(p, 'is_a') and any('DatatypeProperty' in str(a) for a in p.is_a)]
                
                lines.append(f"  Propriétés: {len(obj_props)} objets, {len(data_props)} données")
                if obj_props:
                    lines.append("    Propriétés d'objet:")
                    for prop in sorted(obj_props, key=lambda p: p.name):
                        lines.append(f"      • {prop}")
                if data_props:
                    lines.append("    Propriétés de données:")
                    for prop in sorted(data_props, key=lambda p: p.name):
                        lines.append(f"      • {prop}")
                lines.append("")
        
        # Résumé global
        lines.append("=" * 60)
        lines.append("RÉSUMÉ GLOBAL")
        lines.append("=" * 60)
        lines.append(f"Total ontologies: {len(self.loaded_graphs)}")
        lines.append(f"Total triples: {total_triples}")
        lines.append(f"Total classes: {total_classes}")
        lines.append(f"Total propriétés: {total_properties}")
        lines.append(f"Total individus: {total_individuals}")
        lines.append("")
        
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text('\n'.join(lines), encoding='utf-8')
        return output_file
    
    def generate_html_report(self, output_dir: Path) -> Path:
        """Générer un rapport HTML interactif avec CSS et JS."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Créer le rapport JSON
        json_report = {
            "ontologies_dir": str(self.ontologies_dir),
            "loaded_ontologies": [self.get_statistics(n) for n in self.loaded_graphs],
        }
        
        # Collecter les données détaillées pour chaque ontologie
        ontology_data = {}
        for name in sorted(self.loaded_graphs.keys()):
            graph = self.loaded_graphs[name]
            onto = graph._ontology
            stats = self.get_statistics(name)
            
            # Collecter les classes
            classes = []
            for cls in list(onto.classes()):
                parents = [p.name for p in cls.is_a if hasattr(p, "name") and p.name != "Thing"]
                classes.append({
                    "name": cls.name,
                    "parents": parents
                })
            
            # Collecter les propriétés
            props = list(onto.properties())
            obj_props = []
            data_props = []
            for prop in props:
                if hasattr(prop, 'is_a'):
                    if any('ObjectProperty' in str(a) for a in prop.is_a):
                        obj_props.append(prop.name)
                    elif any('DatatypeProperty' in str(a) for a in prop.is_a):
                        data_props.append(prop.name)
            
            # Visualisation ASCII
            nodes = set()
            edges = []
            
            # Ajouter les classes
            for cls in list(onto.classes())[:15]:
                nodes.add(cls.name)
                for parent in cls.is_a:
                    if hasattr(parent, 'name') and parent.name != 'Thing':
                        edges.append({"source": cls.name, "target": parent.name, "type": "inheritance"})
                        nodes.add(parent.name)
            
            # Ajouter quelques propriétés
            for prop in props[:10]:
                nodes.add(prop.name)
                for subj, pred, obj in onto.get_triples():
                    if len(edges) >= 20:
                        break
                    subj_name = getattr(subj, 'name', str(subj))
                    pred_name = getattr(pred, 'name', str(pred))
                    obj_name = getattr(obj, 'name', str(obj))
                    
                    if pred_name == prop.name and subj_name in nodes and obj_name in nodes:
                        edges.append({"source": subj_name, "target": obj_name, "type": "property"})
                        break
            
            # Créer la grille ASCII
            ascii_graph = ""
            if nodes:
                node_positions = {}
                cols = 4
                sorted_nodes = sorted(list(nodes))
                
                for i, node in enumerate(sorted_nodes):
                    row = i // cols
                    col = i % cols
                    node_positions[node] = (col * 20, row * 4)
                
                grid = {}
                for node, (x, y) in node_positions.items():
                    display_name = node[:12] + "..." if len(node) > 12 else node
                    for j, char in enumerate(display_name):
                        grid[(x + j, y)] = char
                    grid[(x - 1, y)] = '['
                    grid[(x + len(display_name), y)] = ']'
                
                for src, dst, edge_type in edges[:10]:
                    if src in node_positions and dst in node_positions:
                        x1, y1 = node_positions[src]
                        x2, y2 = node_positions[dst]
                        
                        if y1 == y2:
                            for x in range(min(x1, x2) + 1, max(x1, x2)):
                                if (x, y1) not in grid:
                                    grid[(x, y1)] = '─'
                        elif x1 == x2:
                            for y in range(min(y1, y2) + 1, max(y1, y2)):
                                if (x1, y) not in grid:
                                    grid[(x1, y)] = '│'
                
                if grid:
                    min_x = min(pos[0] for pos in grid.keys())
                    max_x = max(pos[0] for pos in grid.keys())
                    min_y = min(pos[1] for pos in grid.keys())
                    max_y = max(pos[1] for pos in grid.keys())
                    
                    ascii_lines = []
                    for y in range(min_y, max_y + 1):
                        line = "    "
                        for x in range(min_x, max_x + 1):
                            line += grid.get((x, y), ' ')
                        ascii_lines.append(line)
                    
                    ascii_graph = '\n'.join(ascii_lines)
                else:
                    ascii_graph = "    [Graphe trop complexe pour la visualisation ASCII]"
            else:
                ascii_graph = "    [Aucun nœud à afficher]"
            
            ontology_data[name] = {
                "stats": stats,
                "classes": classes,
                "object_properties": obj_props,
                "data_properties": data_props,
                "ascii_graph": ascii_graph,
                "edges": edges
            }
        
        # Générer le HTML
        html_content = self._generate_html_template(json_report, ontology_data)
        
        # Générer le CSS
        css_content = self._generate_css_template()
        
        # Générer le JS
        js_content = self._generate_js_template(json_report, ontology_data)
        
        # Écrire les fichiers
        html_file = output_dir / "index.html"
        css_file = output_dir / "style.css"
        js_file = output_dir / "script.js"
        
        html_file.write_text(html_content, encoding='utf-8')
        css_file.write_text(css_content, encoding='utf-8')
        js_file.write_text(js_content, encoding='utf-8')
        
        return html_file
    
    def _generate_html_template(self, json_report, ontology_data):
        """Générer le template HTML."""
        total_ontologies = len(ontology_data)
        total_triples = sum(data["stats"]["triples"] for data in ontology_data.values())
        total_classes = sum(data["stats"]["classes"] for data in ontology_data.values())
        total_properties = sum(data["stats"]["properties"] for data in ontology_data.values())
        
        ontology_sections = ""
        for name, data in ontology_data.items():
            stats = data["stats"]
            classes = data["classes"]
            obj_props = data["object_properties"]
            data_props = data["data_properties"]
            
            classes_list = ""
            for cls in classes[:10]:
                if cls["parents"]:
                    classes_list += f'                <li>{cls["name"]} ← {", ".join(cls["parents"])}</li>\n'
                else:
                    classes_list += f'                <li>{cls["name"]}</li>\n'
            
            if len(classes) > 10:
                classes_list += f'                <li><em>... et {len(classes) - 10} autres classes</em></li>\n'
            
            obj_props_list = ""
            for prop in obj_props[:5]:
                obj_props_list += f'                <li>{prop}</li>\n'
            
            data_props_list = ""
            for prop in data_props[:5]:
                data_props_list += f'                <li>{prop}</li>\n'
            
            ontology_sections += f'''
        <div class="ontology-section" data-ontology="{name}">
            <div class="ontology-header">
                <h2 class="ontology-title">{name.upper()}</h2>
                <div class="ontology-stats">
                    <div class="ontology-stat">
                        <div class="ontology-stat-value">{stats["triples"]}</div>
                        <div class="ontology-stat-label">Triples</div>
                    </div>
                    <div class="ontology-stat">
                        <div class="ontology-stat-value">{stats["classes"]}</div>
                        <div class="ontology-stat-label">Classes</div>
                    </div>
                    <div class="ontology-stat">
                        <div class="ontology-stat-value">{stats["properties"]}</div>
                        <div class="ontology-stat-label">Propriétés</div>
                    </div>
                    <div class="ontology-stat">
                        <div class="ontology-stat-value">{stats["individuals"]}</div>
                        <div class="ontology-stat-label">Individus</div>
                    </div>
                </div>
            </div>
            
            <div class="tabs">
                <button class="tab active" data-tab="graph-{name}">Graphe</button>
                <button class="tab" data-tab="details-{name}">Détails</button>
                <button class="tab" data-tab="json-{name}">JSON</button>
            </div>
            
            <div class="tab-content active" id="graph-{name}">
                <div class="search-box">
                    <input type="text" class="search-input" placeholder="Rechercher dans le graphe..." data-ontology="{name}">
                    <span class="search-icon">🔍</span>
                </div>
                
                <div class="graph-controls">
                    <button class="control-btn">🔄 Reset</button>
                    <button class="control-btn secondary">📐 Fit</button>
                    <button class="control-btn secondary">💾 Export</button>
                </div>
                
                <div class="graph-canvas-container">
                    <canvas id="graph-canvas"></canvas>
                </div>
                
                <div class="legend">
                    <h4>Légende des couleurs:</h4>
                    <div class="legend-items">
                        <div class="legend-item">
                            <div class="legend-color" style="background: #6366f1;"></div>
                            <span class="legend-text">Classes</span>
                        </div>
                        <div class="legend-item">
                            <div class="legend-color" style="background: #ec4899;"></div>
                            <span class="legend-text">Propriétés d'objet</span>
                        </div>
                        <div class="legend-item">
                            <div class="legend-color" style="background: #f59e0b;"></div>
                            <span class="legend-text">Propriétés de données</span>
                        </div>
                        <div class="legend-item">
                            <div class="legend-color" style="background: #10b981;"></div>
                            <span class="legend-text">Héritage</span>
                        </div>
                        <div class="legend-item">
                            <div class="legend-color" style="background: #8b5cf6;"></div>
                            <span class="legend-text">Relations</span>
                        </div>
                    </div>
                </div>
                
                <div style="margin-top: 1rem; padding: 1rem; background: #f8fafb; border-radius: 8px; font-size: 0.9rem; color: #6b7280;">
                    <strong>💡 Contrôles:</strong> 
                    • Glisser les nœuds pour les déplacer 
                    • Molette pour zoomer 
                    • Double-clic pour voir les détails 
                    • Ctrl+F pour rechercher
                </div>
            </div>
            
            <div class="tab-content" id="details-{name}">
                <div class="details-grid">
                    <div class="detail-section">
                        <h4>Classes ({len(classes)})</h4>
                        <ul class="detail-list">
{classes_list}                        </ul>
                    </div>
                    <div class="detail-section">
                        <h4>Propriétés d'objet ({len(obj_props)})</h4>
                        <ul class="detail-list">
{obj_props_list}                        </ul>
                    </div>
                    <div class="detail-section">
                        <h4>Propriétés de données ({len(data_props)})</h4>
                        <ul class="detail-list">
{data_props_list}                        </ul>
                    </div>
                </div>
            </div>
            
            <div class="tab-content" id="json-{name}">
                <div class="json-section">
                    <h4>Données JSON pour {name}</h4>
                    <div class="json-content">{json.dumps(stats, indent=2, ensure_ascii=False)}</div>
                </div>
            </div>
        </div>
'''
        
        return f'''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Rapport des Ontologies NSXAI</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <div class="container">
        <header class="header">
            <h1>Rapport des Ontologies NSXAI</h1>
            <p>Dossier: {json_report["ontologies_dir"]}</p>
        </header>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">{total_ontologies}</div>
                <div class="stat-label">Ontologies</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{total_triples}</div>
                <div class="stat-label">Triples</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{total_classes}</div>
                <div class="stat-label">Classes</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{total_properties}</div>
                <div class="stat-label">Propriétés</div>
            </div>
        </div>
        
        <div class="json-section">
            <h4>Données complètes (JSON)</h4>
            <div class="json-content">{json.dumps(json_report, indent=2, ensure_ascii=False)}</div>
        </div>
        
{ontology_sections}
        
        <footer class="footer">
            <p>Généré par NSXAI Ontology Loader - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </footer>
    </div>
    
    <script src="script.js"></script>
</body>
</html>'''
    
    def _generate_css_template(self):
        """Générer le CSS moderne."""
        return '''/* Modern Ontology Report Styles */
:root {
    --primary: #6366f1;
    --primary-dark: #4f46e5;
    --secondary: #8b5cf6;
    --accent: #ec4899;
    --success: #10b981;
    --warning: #f59e0b;
    --danger: #ef4444;
    --dark: #1f2937;
    --light: #f9fafb;
    --gray: #6b7280;
    --white: #ffffff;
    --shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
    --shadow-lg: 0 20px 40px rgba(0, 0, 0, 0.15);
    --radius: 12px;
    --radius-lg: 20px;
    --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    line-height: 1.6;
    color: var(--dark);
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    min-height: 100vh;
    font-weight: 400;
}

.container {
    max-width: 1400px;
    margin: 0 auto;
    padding: 2rem;
}

.header {
    background: rgba(255, 255, 255, 0.95);
    backdrop-filter: blur(20px);
    border-radius: var(--radius-lg);
    padding: 3rem;
    margin-bottom: 3rem;
    box-shadow: var(--shadow-lg);
    text-align: center;
    border: 1px solid rgba(255, 255, 255, 0.2);
    position: relative;
    overflow: hidden;
}

.header::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 4px;
    background: linear-gradient(90deg, var(--primary), var(--secondary), var(--accent));
}

.header h1 {
    font-size: 3rem;
    font-weight: 800;
    margin-bottom: 1rem;
    background: linear-gradient(135deg, var(--primary), var(--secondary));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    letter-spacing: -0.02em;
}

.header p {
    color: var(--gray);
    font-size: 1.1rem;
    font-weight: 500;
}

.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 2rem;
    margin-bottom: 3rem;
}

.stat-card {
    background: rgba(255, 255, 255, 0.95);
    backdrop-filter: blur(20px);
    border-radius: var(--radius-lg);
    padding: 2rem;
    text-align: center;
    box-shadow: var(--shadow);
    transition: var(--transition);
    border: 1px solid rgba(255, 255, 255, 0.2);
    position: relative;
    overflow: hidden;
}

.stat-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: linear-gradient(90deg, var(--primary), var(--secondary));
    transform: scaleX(0);
    transition: transform 0.3s ease;
}

.stat-card:hover {
    transform: translateY(-8px);
    box-shadow: var(--shadow-lg);
}

.stat-card:hover::before {
    transform: scaleX(1);
}

.stat-number {
    font-size: 3rem;
    font-weight: 800;
    color: var(--primary);
    margin-bottom: 0.5rem;
    line-height: 1;
}

.stat-label {
    color: var(--gray);
    font-size: 0.9rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-weight: 600;
}

.ontology-section {
    background: rgba(255, 255, 255, 0.95);
    backdrop-filter: blur(20px);
    border-radius: var(--radius-lg);
    padding: 2.5rem;
    margin-bottom: 3rem;
    box-shadow: var(--shadow-lg);
    border: 1px solid rgba(255, 255, 255, 0.2);
    position: relative;
    overflow: hidden;
}

.ontology-section::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: linear-gradient(90deg, var(--primary), var(--secondary));
}

.ontology-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 2rem;
    padding-bottom: 1.5rem;
    border-bottom: 1px solid rgba(0, 0, 0, 0.1);
}

.ontology-title {
    font-size: 2rem;
    font-weight: 700;
    color: var(--dark);
    letter-spacing: -0.01em;
}

.ontology-stats {
    display: flex;
    gap: 1.5rem;
}

.ontology-stat {
    text-align: center;
    padding: 1rem 1.5rem;
    background: var(--light);
    border-radius: var(--radius);
    min-width: 90px;
    border: 1px solid rgba(0, 0, 0, 0.05);
    transition: var(--transition);
}

.ontology-stat:hover {
    background: var(--primary);
    color: var(--white);
    transform: translateY(-2px);
}

.ontology-stat-value {
    font-size: 1.8rem;
    font-weight: 700;
    color: inherit;
    line-height: 1;
}

.ontology-stat-label {
    font-size: 0.75rem;
    color: inherit;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-weight: 600;
    margin-top: 0.25rem;
}

.tabs {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 2rem;
    background: var(--light);
    padding: 0.5rem;
    border-radius: var(--radius);
}

.tab {
    padding: 1rem 2rem;
    background: none;
    border: none;
    color: var(--gray);
    cursor: pointer;
    font-size: 1rem;
    font-weight: 600;
    transition: var(--transition);
    border-radius: calc(var(--radius) - 4px);
    position: relative;
}

.tab:hover {
    color: var(--primary);
    background: rgba(99, 102, 241, 0.1);
}

.tab.active {
    color: var(--white);
    background: var(--primary);
    box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}

.tab-content {
    display: none;
    animation: fadeInUp 0.5s ease;
}

.tab-content.active {
    display: block;
}

@keyframes fadeInUp {
    from { 
        opacity: 0; 
        transform: translateY(20px); 
    }
    to { 
        opacity: 1; 
        transform: translateY(0); 
    }
}

.graph-canvas-container {
    background: var(--white);
    border-radius: var(--radius);
    padding: 2rem;
    margin-bottom: 2rem;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
    border: 1px solid rgba(0, 0, 0, 0.05);
    position: relative;
    min-height: 500px;
}

#graph-canvas {
    width: 100%;
    height: 500px;
    border-radius: var(--radius);
}

.graph-controls {
    display: flex;
    gap: 1rem;
    margin-bottom: 2rem;
    flex-wrap: wrap;
}

.control-btn {
    padding: 0.75rem 1.5rem;
    background: var(--primary);
    color: var(--white);
    border: none;
    border-radius: var(--radius);
    cursor: pointer;
    font-weight: 600;
    transition: var(--transition);
    font-size: 0.9rem;
}

.control-btn:hover {
    background: var(--primary-dark);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}

.control-btn.secondary {
    background: var(--secondary);
}

.control-btn.secondary:hover {
    background: #7c3aed;
}

.search-box {
    margin-bottom: 2rem;
    position: relative;
}

.search-input {
    width: 100%;
    padding: 1rem 3rem 1rem 1.5rem;
    border: 2px solid rgba(0, 0, 0, 0.1);
    border-radius: var(--radius);
    font-size: 1rem;
    font-weight: 500;
    transition: var(--transition);
    background: var(--white);
}

.search-input:focus {
    outline: none;
    border-color: var(--primary);
    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.search-icon {
    position: absolute;
    right: 1rem;
    top: 50%;
    transform: translateY(-50%);
    color: var(--gray);
}

.legend {
    background: var(--light);
    border-radius: var(--radius);
    padding: 1.5rem;
    margin-bottom: 2rem;
    border: 1px solid rgba(0, 0, 0, 0.05);
}

.legend h4 {
    color: var(--dark);
    margin-bottom: 1rem;
    font-weight: 600;
}

.legend-items {
    display: flex;
    gap: 2rem;
    flex-wrap: wrap;
}

.legend-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
}

.legend-color {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    border: 2px solid var(--white);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.legend-text {
    font-size: 0.9rem;
    font-weight: 500;
    color: var(--dark);
}

.details-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
    gap: 2rem;
}

.detail-section {
    background: var(--light);
    border-radius: var(--radius);
    padding: 2rem;
    border: 1px solid rgba(0, 0, 0, 0.05);
}

.detail-section h4 {
    color: var(--dark);
    margin-bottom: 1.5rem;
    font-weight: 600;
    font-size: 1.1rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.detail-count {
    background: var(--primary);
    color: var(--white);
    padding: 0.25rem 0.75rem;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 600;
}

.detail-list {
    list-style: none;
    max-height: 300px;
    overflow-y: auto;
}

.detail-list li {
    padding: 0.75rem 0;
    border-bottom: 1px solid rgba(0, 0, 0, 0.05);
    transition: var(--transition);
    font-size: 0.9rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.detail-list li:hover {
    background: rgba(99, 102, 241, 0.05);
    padding-left: 1rem;
}

.detail-list li:last-child {
    border-bottom: none;
}

.detail-icon {
    width: 8px;
    height: 8px;
    background: var(--primary);
    border-radius: 50%;
    flex-shrink: 0;
}

.json-section {
    background: var(--dark);
    border-radius: var(--radius);
    padding: 2rem;
    margin-top: 2rem;
}

.json-section h4 {
    color: var(--white);
    margin-bottom: 1.5rem;
    font-weight: 600;
}

.json-content {
    background: #374151;
    border-radius: var(--radius);
    padding: 1.5rem;
    overflow-x: auto;
    font-family: 'Fira Code', 'Monaco', 'Consolas', monospace;
    font-size: 0.9rem;
    color: #e5e7eb;
    white-space: pre;
    line-height: 1.5;
}

.highlight {
    background: #fef3c7;
    color: #92400e;
    padding: 2px 6px;
    border-radius: 4px;
    font-weight: 600;
}

.footer {
    text-align: center;
    padding: 3rem;
    color: rgba(255, 255, 255, 0.9);
    margin-top: 4rem;
    font-weight: 500;
}

/* Scrollbar styling */
::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}

::-webkit-scrollbar-track {
    background: var(--light);
    border-radius: 4px;
}

::-webkit-scrollbar-thumb {
    background: var(--gray);
    border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
    background: var(--primary);
}

/* Responsive design */
@media (max-width: 768px) {
    .container {
        padding: 1rem;
    }
    
    .header h1 {
        font-size: 2rem;
    }
    
    .ontology-header {
        flex-direction: column;
        gap: 1.5rem;
        align-items: flex-start;
    }
    
    .ontology-stats {
        flex-wrap: wrap;
        justify-content: flex-start;
    }
    
    .tabs {
        flex-wrap: wrap;
    }
    
    .tab {
        flex: 1;
        min-width: 100px;
        text-align: center;
    }
    
    .details-grid {
        grid-template-columns: 1fr;
    }
    
    .graph-controls {
        justify-content: center;
    }
    
    .legend-items {
        flex-direction: column;
        gap: 1rem;
    }
}

/* Dark mode support */
@media (prefers-color-scheme: dark) {
    :root {
        --light: #374151;
        --white: #1f2937;
        --dark: #f9fafb;
        --gray: #9ca3af;
    }
    
    body {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    }
}'''
    
    def _generate_js_template(self, json_report, ontology_data):
        """Générer le JavaScript moderne avec graphe interactif."""
        return f'''// Modern Interactive Ontology Report
document.addEventListener('DOMContentLoaded', function() {{
    // Initialize graph data
    const ontologyData = {json.dumps(ontology_data, ensure_ascii=False)};
    
    // Tab functionality
    const tabs = document.querySelectorAll('.tab');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabs.forEach(tab => {{
        tab.addEventListener('click', function() {{
            const targetTab = this.getAttribute('data-tab');
            
            tabs.forEach(t => t.classList.remove('active'));
            tabContents.forEach(tc => tc.classList.remove('active'));
            
            this.classList.add('active');
            const targetContent = document.getElementById(targetTab);
            if (targetContent) {{
                targetContent.classList.add('active');
                
                // Initialize graph when graph tab is clicked
                if (targetTab && targetTab.includes('graph')) {{
                    const ontologyName = targetTab.replace('graph-', '');
                    initializeGraph(ontologyName);
                }}
            }}
        }});
    }});
    
    // Graph visualization class
    class GraphVisualizer {{
        constructor(canvasId, data) {{
            this.canvas = document.getElementById(canvasId);
            this.ctx = this.canvas.getContext('2d');
            this.data = data;
            this.nodes = [];
            this.edges = [];
            this.positions = new Map();
            this.selectedNode = null;
            this.hoveredNode = null;
            this.isDragging = false;
            this.dragOffset = {{ x: 0, y: 0 }};
            this.zoom = 1;
            this.pan = {{ x: 0, y: 0 }};
            
            this.setupCanvas();
            this.processData();
            this.calculateLayout();
            this.setupEventListeners();
            this.animate();
        }}
        
        setupCanvas() {{
            const rect = this.canvas.getBoundingClientRect();
            this.canvas.width = rect.width;
            this.canvas.height = rect.height;
            
            // High DPI support
            const dpr = window.devicePixelRatio || 1;
            this.canvas.width = rect.width * dpr;
            this.canvas.height = rect.height * dpr;
            this.ctx.scale(dpr, dpr);
            this.canvas.style.width = rect.width + 'px';
            this.canvas.style.height = rect.height + 'px';
        }}
        
        processData() {{
            // Process nodes
            this.data.classes.forEach(cls => {{
                this.nodes.push({{
                    id: cls.name,
                    label: cls.name,
                    type: 'class',
                    color: '#6366f1',
                    size: 20,
                    parents: cls.parents || []
                }});
            }});
            
            // Add properties as nodes
            this.data.object_properties.forEach(prop => {{
                this.nodes.push({{
                    id: prop,
                    label: prop,
                    type: 'property',
                    color: '#ec4899',
                    size: 15
                }});
            }});
            
            this.data.data_properties.forEach(prop => {{
                this.nodes.push({{
                    id: prop,
                    label: prop,
                    type: 'data_property',
                    color: '#f59e0b',
                    size: 15
                }});
            }});
            
            // Process edges
            this.data.edges.forEach(edge => {{
                this.edges.push({{
                    source: edge.source,
                    target: edge.target,
                    type: edge.type,
                    color: edge.type === 'inheritance' ? '#10b981' : '#8b5cf6'
                }});
            }});
        }}
        
        calculateLayout() {{
            const width = this.canvas.width / (window.devicePixelRatio || 1);
            const height = this.canvas.height / (window.devicePixelRatio || 1);
            const centerX = width / 2;
            const centerY = height / 2;
            
            // Force-directed layout
            const nodes = this.nodes.length;
            const angleStep = (2 * Math.PI) / nodes;
            
            this.nodes.forEach((node, i) => {{
                const angle = i * angleStep;
                const radius = Math.min(width, height) * 0.3;
                
                this.positions.set(node.id, {{
                    x: centerX + Math.cos(angle) * radius,
                    y: centerY + Math.sin(angle) * radius,
                    vx: 0,
                    vy: 0
                }});
            }});
            
            // Apply force simulation
            this.applyForces();
        }}
        
        applyForces() {{
            const iterations = 50;
            const k = 100; // Spring constant
            const damping = 0.9;
            
            for (let iter = 0; iter < iterations; iter++) {{
                // Reset forces
                this.positions.forEach(pos => {{
                    pos.fx = 0;
                    pos.fy = 0;
                }});
                
                // Repulsion between nodes
                for (let i = 0; i < this.nodes.length; i++) {{
                    for (let j = i + 1; j < this.nodes.length; j++) {{
                        const node1 = this.nodes[i];
                        const node2 = this.nodes[j];
                        const pos1 = this.positions.get(node1.id);
                        const pos2 = this.positions.get(node2.id);
                        
                        const dx = pos2.x - pos1.x;
                        const dy = pos2.y - pos1.y;
                        const distance = Math.sqrt(dx * dx + dy * dy);
                        
                        if (distance > 0) {{
                            const force = k / (distance * distance);
                            const fx = (dx / distance) * force;
                            const fy = (dy / distance) * force;
                            
                            pos1.fx -= fx;
                            pos1.fy -= fy;
                            pos2.fx += fx;
                            pos2.fy += fy;
                        }}
                    }}
                }}
                
                // Attraction along edges
                this.edges.forEach(edge => {{
                    const pos1 = this.positions.get(edge.source);
                    const pos2 = this.positions.get(edge.target);
                    
                    if (pos1 && pos2) {{
                        const dx = pos2.x - pos1.x;
                        const dy = pos2.y - pos1.y;
                        const distance = Math.sqrt(dx * dx + dy * dy);
                        
                        if (distance > 0) {{
                            const force = distance / k;
                            const fx = (dx / distance) * force;
                            const fy = (dy / distance) * force;
                            
                            pos1.fx += fx;
                            pos1.fy += fy;
                            pos2.fx -= fx;
                            pos2.fy -= fy;
                        }}
                    }}
                }});
                
                // Update positions
                this.positions.forEach(pos => {{
                    pos.vx = (pos.vx + pos.fx) * damping;
                    pos.vy = (pos.vy + pos.fy) * damping;
                    pos.x += pos.vx;
                    pos.y += pos.vy;
                }});
            }}
        }}
        
        setupEventListeners() {{
            this.canvas.addEventListener('mousedown', this.handleMouseDown.bind(this));
            this.canvas.addEventListener('mousemove', this.handleMouseMove.bind(this));
            this.canvas.addEventListener('mouseup', this.handleMouseUp.bind(this));
            this.canvas.addEventListener('wheel', this.handleWheel.bind(this));
            this.canvas.addEventListener('dblclick', this.handleDoubleClick.bind(this));
        }}
        
        handleMouseDown(e) {{
            const rect = this.canvas.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            const node = this.getNodeAt(x, y);
            if (node) {{
                this.selectedNode = node;
                this.isDragging = true;
                const pos = this.positions.get(node.id);
                this.dragOffset = {{
                    x: x - pos.x,
                    y: y - pos.y
                }};
            }}
        }}
        
        handleMouseMove(e) {{
            const rect = this.canvas.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            if (this.isDragging && this.selectedNode) {{
                const pos = this.positions.get(this.selectedNode.id);
                pos.x = x - this.dragOffset.x;
                pos.y = y - this.dragOffset.y;
            }} else {{
                const node = this.getNodeAt(x, y);
                if (node !== this.hoveredNode) {{
                    this.hoveredNode = node;
                    this.canvas.style.cursor = node ? 'pointer' : 'default';
                }}
            }}
        }}
        
        handleMouseUp() {{
            this.isDragging = false;
            this.selectedNode = null;
        }}
        
        handleWheel(e) {{
            e.preventDefault();
            const delta = e.deltaY > 0 ? 0.9 : 1.1;
            this.zoom *= delta;
            this.zoom = Math.max(0.1, Math.min(5, this.zoom));
        }}
        
        handleDoubleClick(e) {{
            const rect = this.canvas.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            const node = this.getNodeAt(x, y);
            if (node) {{
                this.showNodeDetails(node);
            }}
        }}
        
        getNodeAt(x, y) {{
            for (const node of this.nodes) {{
                const pos = this.positions.get(node.id);
                const dx = x - pos.x;
                const dy = y - pos.y;
                const distance = Math.sqrt(dx * dx + dy * dy);
                
                if (distance <= node.size) {{
                    return node;
                }}
            }}
            return null;
        }}
        
        showNodeDetails(node) {{
            const details = document.createElement('div');
            details.style.cssText = `
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background: white;
                padding: 2rem;
                border-radius: 12px;
                box-shadow: 0 20px 40px rgba(0, 0, 0, 0.2);
                z-index: 1000;
                max-width: 400px;
            `;
            
            let content = `
                <h3 style="margin: 0 0 1rem 0; color: #1f2937;">${{node.label}}</h3>
                <p style="margin: 0 0 0.5rem 0; color: #6b7280;">Type: ${{node.type}}</p>
            `;
            
            if (node.parents && node.parents.length > 0) {{
                content += `<p style="margin: 0 0 0.5rem 0; color: #6b7280;">Parents: ${{node.parents.join(', ')}}</p>`;
            }}
            
            details.innerHTML = content;
            
            const closeBtn = document.createElement('button');
            closeBtn.textContent = 'Fermer';
            closeBtn.style.cssText = `
                margin-top: 1rem;
                padding: 0.5rem 1rem;
                background: #6366f1;
                color: white;
                border: none;
                border-radius: 6px;
                cursor: pointer;
            `;
            closeBtn.onclick = () => document.body.removeChild(details);
            
            details.appendChild(closeBtn);
            document.body.appendChild(details);
        }}
        
        draw() {{
            const width = this.canvas.width / (window.devicePixelRatio || 1);
            const height = this.canvas.height / (window.devicePixelRatio || 1);
            
            // Clear canvas
            this.ctx.clearRect(0, 0, width, height);
            
            // Apply transformations
            this.ctx.save();
            this.ctx.translate(this.pan.x, this.pan.y);
            this.ctx.scale(this.zoom, this.zoom);
            
            // Draw edges
            this.edges.forEach(edge => {{
                const pos1 = this.positions.get(edge.source);
                const pos2 = this.positions.get(edge.target);
                
                if (pos1 && pos2) {{
                    this.ctx.beginPath();
                    this.ctx.moveTo(pos1.x, pos1.y);
                    this.ctx.lineTo(pos2.x, pos2.y);
                    this.ctx.strokeStyle = edge.color;
                    this.ctx.lineWidth = 2;
                    this.ctx.globalAlpha = 0.6;
                    this.ctx.stroke();
                    
                    // Draw arrow
                    const angle = Math.atan2(pos2.y - pos1.y, pos2.x - pos1.x);
                    const arrowLength = 10;
                    const arrowAngle = Math.PI / 6;
                    
                    this.ctx.beginPath();
                    this.ctx.moveTo(pos2.x, pos2.y);
                    this.ctx.lineTo(
                        pos2.x - arrowLength * Math.cos(angle - arrowAngle),
                        pos2.y - arrowLength * Math.sin(angle - arrowAngle)
                    );
                    this.ctx.moveTo(pos2.x, pos2.y);
                    this.ctx.lineTo(
                        pos2.x - arrowLength * Math.cos(angle + arrowAngle),
                        pos2.y - arrowLength * Math.sin(angle + arrowAngle)
                    );
                    this.ctx.stroke();
                }}
            }});
            
            // Draw nodes
            this.nodes.forEach(node => {{
                const pos = this.positions.get(node.id);
                if (!pos) return;
                
                const isHovered = node === this.hoveredNode;
                const isSelected = node === this.selectedNode;
                
                // Draw node circle
                this.ctx.beginPath();
                this.ctx.arc(pos.x, pos.y, node.size * (isHovered ? 1.2 : 1), 0, 2 * Math.PI);
                this.ctx.fillStyle = node.color;
                this.ctx.globalAlpha = isSelected ? 1 : 0.8;
                this.ctx.fill();
                
                if (isSelected) {{
                    this.ctx.strokeStyle = '#1f2937';
                    this.ctx.lineWidth = 3;
                    this.ctx.stroke();
                }}
                
                // Draw label
                this.ctx.fillStyle = '#1f2937';
                this.ctx.font = '12px Inter, sans-serif';
                this.ctx.textAlign = 'center';
                this.ctx.textBaseline = 'middle';
                this.ctx.globalAlpha = 1;
                
                // Truncate long labels
                let label = node.label;
                if (label.length > 15) {{
                    label = label.substring(0, 12) + '...';
                }}
                
                this.ctx.fillText(label, pos.x, pos.y + node.size + 15);
            }});
            
            this.ctx.restore();
        }}
        
        animate() {{
            this.draw();
            requestAnimationFrame(() => this.animate());
        }}
    }}
    
    // Initialize graph for ontology
    function initializeGraph(ontologyName) {{
        const data = ontologyData[ontologyName];
        if (!data) return;
        
        // Check if canvas exists
        let canvas = document.getElementById('graph-canvas');
        if (!canvas) {{
            // Create canvas
            const container = document.querySelector(`[data-ontology="${{ontologyName}}"] .graph-canvas-container`);
            if (container) {{
                canvas = document.createElement('canvas');
                canvas.id = 'graph-canvas';
                container.appendChild(canvas);
            }}
        }}
        
        if (canvas) {{
            new GraphVisualizer('graph-canvas', data);
        }}
    }}
    
    // Search functionality
    const searchInputs = document.querySelectorAll('.search-input');
    
    searchInputs.forEach(input => {{
        input.addEventListener('input', function() {{
            const searchTerm = this.value.toLowerCase();
            const ontologyName = this.getAttribute('data-ontology');
            
            // Highlight nodes in graph
            if (window.currentGraph) {{
                window.currentGraph.nodes.forEach(node => {{
                    const isMatch = node.label.toLowerCase().includes(searchTerm);
                    node.highlighted = isMatch;
                }});
            }}
            
            // Highlight in text content
            const graphContainer = this.parentElement.nextElementSibling;
            if (graphContainer && !graphContainer.querySelector('canvas')) {{
                const originalText = graphContainer.textContent;
                
                if (searchTerm === '') {{
                    const highlighted = graphContainer.querySelectorAll('.highlight');
                    highlighted.forEach(el => {{
                        const parent = el.parentNode;
                        parent.replaceChild(document.createTextNode(el.textContent), el);
                        parent.normalize();
                    }});
                }} else {{
                    const highlighted = graphContainer.querySelectorAll('.highlight');
                    highlighted.forEach(el => {{
                        const parent = el.parentNode;
                        parent.replaceChild(document.createTextNode(el.textContent), el);
                        parent.normalize();
                    }});
                    
                    const text = graphContainer.textContent;
                    const regex = new RegExp(`(${{searchTerm}})`, 'gi');
                    const matches = text.match(regex);
                    
                    if (matches) {{
                        let highlightedText = text;
                        const uniqueMatches = [...new Set(matches.map(m => m.toLowerCase()))];
                        
                        uniqueMatches.forEach(match => {{
                            const matchRegex = new RegExp(`(${{match}})`, 'gi');
                            highlightedText = highlightedText.replace(matchRegex, '<span class="highlight">$1</span>');
                        }});
                        
                        graphContainer.innerHTML = highlightedText;
                    }}
                }}
            }}
        }});
    }});
    
    // Graph controls
    document.querySelectorAll('.control-btn').forEach(btn => {{
        btn.addEventListener('click', function() {{
            const action = this.textContent.toLowerCase();
            
            if (window.currentGraph) {{
                switch(action) {{
                    case 'reset':
                        window.currentGraph.zoom = 1;
                        window.currentGraph.pan = {{ x: 0, y: 0 }};
                        break;
                    case 'fit':
                        // Fit graph to view
                        window.currentGraph.zoom = 0.8;
                        break;
                    case 'export':
                        // Export graph as image
                        const canvas = document.getElementById('graph-canvas');
                        const link = document.createElement('a');
                        link.download = 'ontology-graph.png';
                        link.href = canvas.toDataURL();
                        link.click();
                        break;
                }}
            }}
        }});
    }});
    
    // Keyboard shortcuts
    document.addEventListener('keydown', function(e) {{
        if ((e.ctrlKey || e.metaKey) && e.key === 'f') {{
            e.preventDefault();
            const firstSearchInput = document.querySelector('.search-input');
            if (firstSearchInput) {{
                firstSearchInput.focus();
            }}
        }}
        
        if (e.key === 'Escape') {{
            searchInputs.forEach(input => {{
                input.value = '';
                input.dispatchEvent(new Event('input'));
            }});
        }}
    }});
    
    // Print functionality
    const printBtn = document.createElement('button');
    printBtn.innerHTML = '🖨️ Imprimer';
    printBtn.className = 'control-btn';
    printBtn.style.cssText = `
        position: fixed;
        top: 2rem;
        right: 2rem;
        z-index: 1000;
        box-shadow: 0 10px 25px rgba(0, 0, 0, 0.2);
    `;
    printBtn.addEventListener('click', () => window.print());
    document.body.appendChild(printBtn);
    
    console.log('🎨 Modern ontology report loaded successfully!');
}});'''
    
    def generate_graph_report(self, output_path: str) -> Path:
        """Générer un rapport texte avec visualisation de graphe ASCII."""
        lines = []
        lines.append("=" * 80)
        lines.append("RAPPORT DE GRAPHE DES ONTOLOGIES")
        lines.append("=" * 80)
        lines.append(f"Dossier: {self.ontologies_dir}")
        lines.append(f"Ontologies chargées: {len(self.loaded_graphs)}")
        lines.append("")
        
        for name in sorted(self.loaded_graphs.keys()):
            graph = self.loaded_graphs[name]
            onto = graph._ontology
            stats = self.get_statistics(name)
            
            lines.append(f"{'─' * 60}")
            lines.append(f"ONTOLOGIE: {name.upper()}")
            lines.append(f"{'─' * 60}")
            lines.append(f"  Triples:     {stats['triples']}")
            lines.append(f"  Classes:     {stats['classes']}")
            lines.append(f"  Propriétés:  {stats['properties']}")
            lines.append(f"  Individus:   {stats['individuals']}")
            lines.append("")
            
            # Visualisation ASCII du graphe
            lines.append("  VISUALISATION DU GRAPHE:")
            lines.append("  " + "─" * 50)
            
            # Collecter les nœuds et relations
            nodes = set()
            edges = []
            
            # Ajouter les classes
            classes = list(onto.classes())
            for cls in classes[:15]:  # Limiter pour la lisibilité
                nodes.add(cls.name)
                # Relations d'héritage
                for parent in cls.is_a:
                    if hasattr(parent, 'name') and parent.name != 'Thing':
                        edges.append((cls.name, parent.name, 'inheritance'))
                        nodes.add(parent.name)
            
            # Ajouter quelques propriétés importantes
            props = list(onto.properties())[:10]
            for prop in props:
                nodes.add(prop.name)
                # Relations d'utilisation (exemples)
                for subj, pred, obj in onto.get_triples():
                    if len(edges) >= 20:  # Limiter les arêtes
                        break
                    subj_name = getattr(subj, 'name', str(subj))
                    pred_name = getattr(pred, 'name', str(pred))
                    obj_name = getattr(obj, 'name', str(obj))
                    
                    if pred_name == prop.name and subj_name in nodes and obj_name in nodes:
                        edges.append((subj_name, obj_name, 'property'))
                        break
            
            # Créer la visualisation ASCII
            if nodes:
                # Positionnement simple des nœuds
                node_positions = {}
                cols = 4
                sorted_nodes = sorted(list(nodes))
                
                for i, node in enumerate(sorted_nodes):
                    row = i // cols
                    col = i % cols
                    node_positions[node] = (col * 20, row * 4)
                
                # Dessiner les nœuds
                grid = {}
                for node, (x, y) in node_positions.items():
                    # Tronquer les noms longs
                    display_name = node[:12] + "..." if len(node) > 12 else node
                    for j, char in enumerate(display_name):
                        grid[(x + j, y)] = char
                    grid[(x - 1, y)] = '['
                    grid[(x + len(display_name), y)] = ']'
                
                # Dessiner les arêtes (simplifié)
                for src, dst, edge_type in edges[:10]:
                    if src in node_positions and dst in node_positions:
                        x1, y1 = node_positions[src]
                        x2, y2 = node_positions[dst]
                        
                        # Ligne horizontale simple
                        if y1 == y2:
                            for x in range(min(x1, x2) + 1, max(x1, x2)):
                                if (x, y1) not in grid:
                                    grid[(x, y1)] = '─'
                        # Ligne verticale simple
                        elif x1 == x2:
                            for y in range(min(y1, y2) + 1, max(y1, y2)):
                                if (x1, y) not in grid:
                                    grid[(x1, y)] = '│'
                
                # Générer la grille ASCII
                if grid:
                    min_x = min(pos[0] for pos in grid.keys())
                    max_x = max(pos[0] for pos in grid.keys())
                    min_y = min(pos[1] for pos in grid.keys())
                    max_y = max(pos[1] for pos in grid.keys())
                    
                    for y in range(min_y, max_y + 1):
                        line = "    "
                        for x in range(min_x, max_x + 1):
                            line += grid.get((x, y), ' ')
                        lines.append(line)
                else:
                    lines.append("    [Graphe trop complexe pour la visualisation ASCII]")
            else:
                lines.append("    [Aucun nœud à afficher]")
            
            lines.append("")
            
            # Légende
            lines.append("  LÉGENDE:")
            lines.append("    [Nom]      = Classe/Propriété")
            lines.append("    ─, │      = Relations")
            lines.append("    →          = Direction de la relation")
            lines.append("")
            
            # Statistiques détaillées
            if stats['classes'] > 0:
                lines.append("  DÉTAIL DES CLASSES:")
                classes = list(onto.classes())
                for cls in sorted(classes, key=lambda c: c.name)[:10]:
                    parents = [p.name for p in cls.is_a if hasattr(p, "name") and p.name != "Thing"]
                    if parents:
                        lines.append(f"    {cls.name} ← {', '.join(parents)}")
                    else:
                        lines.append(f"    {cls.name}")
                if len(classes) > 10:
                    lines.append(f"    ... et {len(classes) - 10} autres classes")
                lines.append("")
            
            if stats['properties'] > 0:
                lines.append("  DÉTAIL DES PROPRIÉTÉS:")
                props = list(onto.properties())
                obj_props = [p for p in props if hasattr(p, 'is_a') and any('ObjectProperty' in str(a) for a in p.is_a)]
                data_props = [p for p in props if hasattr(p, 'is_a') and any('DatatypeProperty' in str(a) for a in p.is_a)]
                
                lines.append(f"    Propriétés d'objet: {len(obj_props)}")
                lines.append(f"    Propriétés de données: {len(data_props)}")
                
                if obj_props:
                    for prop in sorted(obj_props, key=lambda p: p.name)[:5]:
                        lines.append(f"      • {prop.name}")
                if data_props:
                    for prop in sorted(data_props, key=lambda p: p.name)[:5]:
                        lines.append(f"      • {prop.name}")
                lines.append("")
        
        lines.append("=" * 80)
        lines.append("FIN DU RAPPORT")
        lines.append("=" * 80)
        
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text('\n'.join(lines), encoding='utf-8')
        return output_file


# ─── Fonctions de commodité ───────────────────────────────────────────────────

_global_loader = OntologyLoader()


def load_ontology(name: str) -> OntologyGraph:
    return _global_loader.load_ontology(name)


def load_all_ontologies() -> Dict[str, OntologyGraph]:
    loader = OntologyLoader()
    for filepath in loader.ontologies_dir.glob("*.owl"):
        try:
            loader.load_ontology(filepath.stem)
        except Exception:
            continue
    return loader.loaded_graphs


def load_from_path(filepath: Path) -> OntologyGraph:
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(filepath)
    onto = get_ontology(str(filepath.resolve()))
    onto.load(only_local=True)
    return OntologyGraph(onto)


def visualize_ontology(ontology: OntologyGraph, method: str = "summary") -> None:
    onto = ontology._ontology if hasattr(ontology, "_ontology") else ontology
    if method == "summary":
        print(f"\n── Summary {'─'*40}")
        print(f"  Classes:     {len(list(onto.classes()))}")
        print(f"  Properties:  {len(list(onto.properties()))}")
        print(f"  Individuals: {len(list(onto.individuals()))}")
    elif method == "hierarchy":
        print(f"\n── Hierarchy {'─'*38}")
        for cls in onto.classes():
            parents = [p.name for p in cls.is_a if hasattr(p, "name")]
            suffix = f"  ← {', '.join(parents)}" if parents else ""
            print(f"  {cls.name}{suffix}")