# Guide — Parent / Parent Guide

## Français

### Lier un enfant <a id="lier-enfant"></a>
Un parent crée son compte (`/auth/login` avec rôle `parent`), puis lie son enfant via `/users/{parent_id}/children` ou `/users/{parent_id}/children` (POST). L'enfant doit avoir un `pseudo` existant.

### Voir la progression <a id="voir-progression"></a>
Le tableau de bord parent (`/dashboard/parent`) affiche la progression des enfants liés : points gagnés (`/rewards`), résultats d'évaluations (`/evaluations`), historique des exercices (`/exercises/history`). Les données sont isolées par `student_pseudo`.

---

## English

### Link a child <a id="lier-enfant-en"></a>
A parent creates an account (`/auth/login` with role `parent`), then links their child via `/users/{parent_id}/children` (POST). The child must have an existing `pseudo`.

### View progress <a id="voir-progression-en"></a>
The parent dashboard (`/dashboard/parent`) shows linked children's progress: points earned (`/rewards`), evaluation results (`/evaluations`), exercise history (`/exercises/history`). Data is isolated by `student_pseudo`.
