# Web - Interface Utilisateur NSXAI

Ce dossier contient l'interface graphique du framework NSXAI.

## Structure

```
web/
├── src/                         # Code source principal
├── components/                  # Composants réutilisables
├── pages/                       # Pages/routes de l'application
├── styles/                      # CSS, Tailwind, thèmes
└── public/                      # Assets statiques (images, fonts)
```

## Stack recommandée

- **Framework** : React / Next.js / Vue.js
- **Styling** : Tailwind CSS
- **State Management** : Zustand / Redux
- **HTTP Client** : Axios / Fetch
- **UI Components** : shadcn/ui ou Headless UI

## Développement

```bash
# Se déplacer dans le dossier web
cd web

# Installation
npm install

# Démarrage en mode dev
npm run dev
```

## Fonctionnalités prévues

- Visualisation du Knowledge Graph
- Exploration des ontologies
- Interface de prédiction avec explications
- Dashboard de monitoring des modèles
- Visualisation des embeddings
