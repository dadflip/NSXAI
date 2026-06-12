NSXAI - MLOps Dataset Export (Enriched Adjacency Matrix)
==========================================================

Ce jeu de données a été exporté sous forme d'une Matrice d'Adjacence Enrichie unique.

### Fichier exporté :
- ontology_matrix.csv : Contient les sources en lignes (colonne `id`), les prédicats en colonnes, et les objets dans les cellules. Les objets multiples pour un même prédicat sont séparés par des pipes (|).

### Comment utiliser pour le ML :
Ce format vous permet d'avoir toutes les features d'un noeud sur une seule ligne. Si vous avez besoin d'extraire des arêtes (edges), vous pouvez dépivoter ou filtrer les colonnes correspondant aux `ObjectProperties` dans Pandas.
