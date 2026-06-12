# NSXAI - Neuro-Symbolic Explainable Artificial Intelligence

Pipeline sémantique complet pour transformer des ontologies OWL/RDF en graphe de connaissances, avec base de données (Apache Jena Fuseki), Intelligence Artificielle intégrée (GNN/MLP via PyTorch/Scikit-Learn), API FastAPI et une interface Web unifiée pour explorer vos données et recevoir des recommandations IA.

---

## 📖 Tutoriel de A à Z : De la mise en place à l'utilisation

Bienvenue dans le guide complet de NSXAI. Ce tutoriel vous accompagnera pas à pas pour installer le projet, le démarrer, et utiliser pleinement l'interface d'exploration et d'IA.

### Étape 1 : Prérequis système

Avant de commencer, assurez-vous d'avoir installé sur votre machine :
- **Python 3.10 ou 3.11** (obligatoire pour la compatibilité IA/PyTorch)
- **Node.js 18+** (nécessaire pour lancer l'interface utilisateur Vite/React)
- **Java 11+** (nécessaire pour faire tourner la base de données Apache Jena Fuseki)

### Étape 2 : Installation du projet

1. **Cloner le dépôt**
   ```bash
   git clone https://github.com/votre-org/NSXAI.git
   cd NSXAI
   ```

2. **Créer l'environnement virtuel Python**
   Il est vivement recommandé d'utiliser un environnement virtuel.
   - *Windows (PowerShell)* :
     ```powershell
     python -m venv venv
     .\venv\Scripts\Activate.ps1
     ```
   - *Linux / macOS* :
     ```bash
     python -m venv venv
     source venv/bin/activate
     ```

3. **Installer les dépendances**
   ```bash
   pip install -r requirements.txt
   ```
   *(Lors du premier lancement du projet, Apache Jena Fuseki et le frontend Node.js seront automatiquement installés et configurés, aucune manipulation complexe n'est requise !)*

---

### Étape 3 : Ajouter vos données (Ontologies)

NSXAI est vide par défaut. Pour l'alimenter, il vous suffit de déposer vos fichiers d'ontologies (fichiers `.owl`, `.ttl`, `.rdf`) dans le dossier prévu à cet effet :
👉 **Dossier : `ontologies/owl/`**

Une fois vos fichiers placés dans ce dossier, le système s'occupera automatiquement de les ingérer dans la base de données lors du démarrage.

---

### Étape 4 : Lancer l'application

Le projet intègre un gestionnaire centralisé ultra-puissant (`nsxai_cli.py`) qui s'occupe de tout démarrer en parallèle : la base de données, l'API IA et le Frontend Web.

Lancez simplement cette commande à la racine du projet :
- *Windows* : `nsxai.bat dev`
- *Linux / macOS* : `./nsxai.sh dev`

**Que se passe-t-il alors ?**
1. Le gestionnaire vérifie si Java, Node et Python sont bien présents.
2. Il télécharge Apache Jena Fuseki si ce n'est pas déjà fait.
3. Il initialise la base de données avec vos fichiers du dossier `ontologies/owl/`.
4. Il démarre l'API Python sur `http://localhost:8000`.
5. Il démarre l'interface Web Vite sur `http://localhost:5173`.

🎉 **L'application est prête ! Ouvrez votre navigateur sur : [http://localhost:5173](http://localhost:5173)**

---

### Étape 5 : Guide d'utilisation de l'Interface

L'interface NSXAI a été refondue pour être sobre, professionnelle et intuitive. Elle est divisée en deux onglets principaux : **Ontology** et **Matrix**.

#### Onglet 1 : L'Explorateur d'Ontologie (Ontology)
Cet onglet vous permet de naviguer dans votre graphe de connaissances de manière arborescente.

1. **L'Arbre de Connaissances (Panneau de gauche)**
   - Il affiche l'arborescence de toutes les entités, classes, et propriétés de votre ontologie.
   - Cliquez sur un nœud pour le sélectionner.
   - L'icône de rafraichissement (Reset) en haut permet de réinitialiser la vue et de purger la base si vous avez modifié vos fichiers d'ontologie.

2. **Détails de l'Entité (Panneau central)**
   - Quand un nœud est sélectionné, ses détails (métadonnées, attributs, propriétés) s'affichent sous forme de cartes.
   - Si une propriété cible un autre nœud (texte en bleu souligné au survol), vous pouvez cliquer dessus pour naviguer (comme sur Wikipédia).
   - Les flèches "Précédent/Suivant" en haut à droite vous permettent de naviguer dans votre historique.

3. **Recommandations IA (Gamification & Découverte)**
   - Sous les détails, le moteur de Machine Learning (GNN / MLP) tourne en arrière-plan.
   - Il prédit de nouvelles liaisons sémantiques (ex: *L'entité devrait-elle être associée à cette cible ?*).
   - Chaque prédiction affiche :
     - **NS Score** (Neuro-symbolic Score) : Le taux de certitude final de l'IA (intégrant les heuristiques et les probabilités neuronales).
     - **L'explication** : Des pavés explicatifs décrivant *pourquoi* l'IA suggère cette liaison (raisonnement structurel, poids numérique, pivot sémantique).

#### Onglet 2 : L'Éditeur Matriciel (Matrix)
Cet onglet est pensé pour la manipulation de données en masse, l'édition, et les simulations "What-if".

1. **La Vue Tableau**
   - Affiche toutes les entités (sujets) ligne par ligne avec leurs propriétés (prédicats) en colonnes.
   - **Recherche globale** (en haut à gauche) : Permet de trouver une entité spécifique.
   - **Filtre de colonnes** : Permet de n'afficher que les propriétés qui vous intéressent (par nom de propriété).

2. **Édition des Données**
   - Double-cliquez sur n'importe quelle cellule du tableau pour l'éditer.
   - Une fenêtre (Modale) s'ouvre, vous permettant d'ajouter des valeurs existantes (autocomplétion puissante depuis le graphe) ou d'ajouter de nouvelles valeurs URI/texte.
   - Sauvegardez : la base de données est instantanément mise à jour (sauf en mode Scenario) !

3. **Simulation (Scenario Mode)**
   - En haut à droite, activez le mode **Scenario** (icône Fiole).
   - Vos modifications ne sont alors *plus envoyées immédiatement* à la base de données.
   - Les cellules modifiées sont surlignées en jaune.
   - Cela vous permet de préparer des modifications massives, de vérifier la cohérence, puis de valider l'ensemble en cliquant sur **Apply**, ou d'annuler avec **Cancel**.

4. **Duplication & Création**
   - Sélectionnez une ligne puis utilisez le bouton **Duplicate Row**. L'application vous demandera combien de copies (ex: 50) vous souhaitez générer (idéal pour la Data Augmentation).
   - Utilisez **Entity** (icône Plus) pour créer manuellement une nouvelle entité vierge depuis l'interface.

5. **Export ML**
   - Le bouton **Export CSV** permet de télécharger un jeu de données "aplatit" de votre graphe complet, prêt à être ingéré par des modèles de Machine Learning externes (comme XGBoost ou LightGBM).

---

### Étape 6 : Entraînement de l'IA (Machine Learning)

Les recommandations neuronales affichées dans l'onglet *Ontology* dépendent d'un modèle d'IA entraîné spécifiquement sur **vos** données.

Pour lancer un entraînement sur vos données fraîchement importées, ouvrez un terminal, activez votre environnement virtuel et lancez le pipeline d'apprentissage autonome MLOps :
```bash
python -m nsxai.ml.main --step all --dim 64
```
Le pipeline automatisé va :
1. Analyser le graphe Fuseki en temps réel.
2. Générer des embeddings topologiques de nœuds via DeepWalk / GCN.
3. Entraîner plusieurs modèles de prédiction de liens.
4. Sauvegarder automatiquement le **meilleur modèle** dans le "Bundle Inference" afin que l'interface Web puisse l'exploiter en direct !

---

## 🛠️ Commandes CLI Avancées (`nsxai.sh` / `nsxai.bat`)

Le script centralisé peut gérer individuellement chaque service, ce qui est utile pour le debug :

```bash
# Gérer les processus individuellement
./nsxai.sh start fuseki     # Démarrer uniquement la base de données
./nsxai.sh start api        # Démarrer uniquement l'API Python
./nsxai.sh start frontend   # Démarrer uniquement l'interface Web Vite
./nsxai.sh stop frontend    # Arrêter le frontend
./nsxai.sh stop all         # Tout éteindre proprement (graceful shutdown)
./nsxai.sh status           # Voir l'état de chaque composant
./nsxai.sh reset            # Purger la base de données et recharger depuis ontologies/owl/
```

*(Sous Windows, utilisez systématiquement `nsxai.bat` au lieu de `./nsxai.sh`)*

---

## 🔧 Configuration Avancée (`config.yaml`)

L'architecture est entièrement paramétrable via le fichier `config.yaml` à la racine :

```yaml
fuseki:
  url: http://localhost:3030
  dataset: nsxai

api:
  host: localhost
  port: 8000
  cors_origins:
    - "http://localhost:5173"

frontend:
  port: 5173
```
Vous pouvez modifier les ports de l'API ou du Frontend, ou encore le nom du dataset Fuseki utilisé par le système pour le cloisonnement de différents projets.

---
**NSXAI Core System** - Architecture modulaire pour Graphes de Connaissances.
