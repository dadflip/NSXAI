# Ontology Network for NSXAI Gamified ITS

## Vue d'ensemble
Ce dossier contient un ensemble d'ontologies OWL pour la modélisation d'un système tutoriel intelligent gamifié (GATO). La structure suit une hiérarchie logique :

1. `gado_core.owl` : concepts fondamentaux de la gamification
2. `gado_full.owl` : extension de GADO Core avec archetypes, affordances et pratiques de conception
3. `its_domain.owl` : ontologie du domaine ITS, issues des ontologies MeuTutor
4. `its_pedagogical.owl` : ontologie pédagogique ITS construite sur `its_domain.owl`
5. `gato.owl` : intégration finale entre gamification (`gado_full.owl`) et ITS pédagogique (`its_pedagogical.owl`)
6. `catalog-v001.xml` : catalogue de résolution des URI locales pour charger les ontologies sans accès réseau

## Liens et imports

- `gado_full.owl` importe `gado_core.owl`
- `gato.owl` importe :
  - `gado_full.owl`
  - `http://surveys.nees.com.br/ontologies/its/its.pedagogical.owl` (mappé localement par `catalog-v001.xml` vers `its_pedagogical.owl`)
- `its_pedagogical.owl` importe `its_domain.owl`
- `GamificationModel` et `hasActivityLoops` ont été déplacés vers `gado_full.owl` pour rassembler les structures de gamification dans la couche GADO.
- `its_domain.owl` utilise de nombreuses définitions externes MeuTutor (`MeuTutor.Domain.owl`, `MeuTutor.Domain.CP.owl`, `MeuTutor.Domain.Curriculum.owl`, `MeuTutor.Pedagogical.owl`, `MeuTutor.Domain.Resource.owl`)

## Recommandations d'organisation

- `catalog-v001.xml` est la référence locale pour la résolution d'URI. Il doit rester aligné avec les IRI des imports.
- `gato.owl` est le point d'entrée principal : il représente l'architecture complète du Gamified ITS.
- `its_domain.owl` et `its_pedagogical.owl` doivent rester séparés pour isoler le modèle de domaine des modèles pédagogiques.
- `gado_core.owl` et `gado_full.owl` doivent rester séparés pour conserver une couche de base et une couche d'extension claire.

## Correction appliquée

- `its_pedagogical.owl` avait une balise `<owl:Ontology rdf:about="">`. Ce fichier a été corrigé pour déclarer correctement son IRI :
  `http://surveys.nees.com.br/ontologies/its/its.pedagogical.owl`

## Points de vigilance

- Les ontologies `gato.owl` et `its_domain.owl` référencent des ontologies externes MeuTutor. Si ces fichiers ne sont pas présents localement, un catalogue ou une redirection doit être ajouté.
- Vérifier que les `ontologyIRI` et les préfixes sont cohérents entre les fichiers et le catalogue.
- Si vous souhaitez rendra la suite plus lisible, vous pouvez uniformiser les préfixes locaux (`gc`, `gf`, `itsp`) et ajouter des commentaires structurés au début de chaque fichier.
