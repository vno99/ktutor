---
id: s16-dashboard-eleve
story: docs/stories.md § s16-dashboard-eleve (lignes 797-830)
base_commit: 690c0c5
date: 2026-09-04
---

# Research — s16-dashboard-eleve

## Résumé en une ligne

La story demande un dashboard élève (endpoint `GET /api/dashboard/eleve` + page `/dashboard/eleve` + cache 5 min + 2 tests) ; **trois prémisses de la story ne tiennent pas dans le code actuel** — (a) `score_avg` n'existe pas car `Attempt` ne stocke qu'un booléen `is_success`, (b) `last_activity_at` n'est pas sur `Attempt` ni `Exercise`, et (c) la dépendance frontend `recharts` n'est pas installée. La s16 est techniquement faisable mais demande des **arbitrages** que le plan doit acter explicitement.

## Périmètre de la story (deps vérifiées)

Source : `docs/stories.md` (AC #1 à #6, complexité déclarée 3) + ADR 005 § JWT, ADR 011 § pseudo cookie.

| Dépendance | Statut sur `main` | Évidence |
| --- | --- | --- |
| Auth JWT + `Depends(get_current_user)` (s13) | ✅ livré | `app/core/auth/middleware.py:58-103` |
| `require_role(["eleve"])` (s13b) | ✅ livré | `app/core/auth/middleware.py:106-135` |
| Modèle `User` (s12) | ✅ livré | `app/core/database/models.py:224-266` |
| Modèle `Attempt` avec `student_pseudo` FK (s04 + s15) | ✅ livré | `app/core/database/models.py:160-207` |
| Modèle `Exercise` avec `subject` (s03) | ✅ livré | `app/core/database/models.py:101-157` |
| Frontend `useAuthStore.isAuthenticated` + `role` (s13) | ✅ livré | `frontend/lib/stores/authStore.ts:75-103` |
| Frontend interceptor `Authorization: Bearer` (s13) | ✅ livré | `frontend/lib/api.ts:128-135` |
| Frontend `recharts` | ❌ **absent** | `frontend/package.json` (ni prod ni dev) |
| Tables `evaluations`, `conversations`, `messages`, `reward_ledger`, `user_points`, `notifications` | ❌ **n'existent pas en code** | `app/core/database/models.py` ne les définit pas |
| Route group frontend `(dashboard)/` | ❌ **n'existe pas** | `frontend/app/` ne contient que `(public)/` |
| Cache backend (Redis / `cachetools` / TTL) | ❌ **n'existe pas** | `requirements.txt` ne contient ni `redis` ni `cachetools` |
| Squelette dashboard (router, page, charts) | ❌ **à créer** | `app/api/dashboard/` absent, `frontend/app/(dashboard)/eleve/dashboard/page.tsx` absent |

**Conséquence** : la s16 est la **première story** à introduire trois familles de code : le sous-domaine `app/api/dashboard/`, la route group frontend `(dashboard)/`, et la dépendance `recharts`. Aucun de ces socles n'est amorti sur du code préexistant. C'est un signal de « story trop large » à regarder de près (cf. § Split).

## Faits structurants vérifiés dans le code

### Fait 1 — `Attempt` n'a pas de score numérique, juste un booléen

`app/core/database/models.py:160-200` :

```python
class Attempt(Base):
    is_success: Mapped[bool] = mapped_column(nullable=False)
    raw_answers: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    answer_text: Mapped[str | None] = mapped_column(String(8192), nullable=True)
    correction_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    submitted_at: Mapped[datetime] = ...
```

L'AC #1 demande `score_avg` par matière. Le code ne stocke rien de numérique — ni dans `Attempt`, ni dans `Exercise` (le QCM laisse `expected_answer` NULL et la solution est reconstruite côté service, `app/services/correction/progressive.py:390-403`).

**Deux lectures possibles** :
- (a) **Taux de réussite** : `score_avg = mean(Attempt.is_success)` par matière. Numériquement entre 0 et 1, multiplicable par 100 pour un % affiché. Sémantiquement honnête (« % de bonnes réponses ») mais différent de « score moyen » au sens où l'élève l'entend.
- (b) **Attendre un score numérique** : refuser d'implémenter `score_avg` tant que la donnée n'existe pas. Reporter l'AC à une story ultérieure (s04b, s07b, s18b) qui introduit `score: float | None` sur `Attempt`.

Le `correction_level` ("partial", "full", etc.) est une chaîne, pas un score. On peut en dériver un **proxy** grossier : `full` ou `full_after_attempts` → 1.0 ; `partial` ou `partial_attempt_2` → 0.5. Mais c'est un signal métier distinct, et la story s16 n'en fait pas mention.

**Recommandation** : la story doit acter explicitement (a) ou (b). Le défaut prudent = (a) avec un label UI clair (« Taux de réussite : 75 % » et non « Score moyen : 75 % »), pour ne pas induire l'élève en erreur. C'est l'arbitrage le plus important du plan.

### Fait 2 — `last_activity_at` n'existe pas sur `Attempt` ni `Exercise`

L'AC #1 demande `last_activity_at` par matière. Tables existantes :

| Table | Colonnes temporelles |
| --- | --- |
| `documents.created_at` | ✅ |
| `exercises.created_at` | ✅ (`app/core/database/models.py:147-151`) |
| `attempts.submitted_at` | ✅ (`app/core/database/models.py:196-200`) |
| `users.created_at` | ✅ |

**Source de `last_activity_at` par matière** : on a le choix entre :
- (i) `MAX(attempts.submitted_at)` joint à `exercises` filtré par `subject` et `student_pseudo` — i.e. la dernière tentative d'exercice.
- (ii) Idem mais unionné avec `MAX(documents.created_at)` (un upload est aussi une activité).
- (iii) Une table `conversations.last_activity_at` qui n'existe pas encore (l'architecture la prévoit, ligne 277, mais aucune story ne l'a créée — elle tomberait avec le chat history, story suivante).

**Recommandation** : (i) pour s16 — on a la donnée, c'est le plus naturel. Étendre à (ii) si l'AC le demande ; ne pas inventer (iii) (sera fait par la story chat-history).

### Fait 3 — `exercises_count` est trivial (`COUNT(attempts)` ou `COUNT(DISTINCT exercise_id)`)

L'AC #1 demande `exercises_count` par matière. Question à trancher : « combien d'exercices tentés » (= `COUNT(attempts)`) ou « combien d'exercices uniques tentés » (= `COUNT(DISTINCT attempts.exercise_id)`) ? Le label UI attendu oriente : « 12 exercices tentés » parle mieux à un parent/élève comme nombre de tentatives.

**Recommandation** : `COUNT(attempts.id)` (= nombre de tentatives) — l'AC dit « exercices tentés » au pluriel sans préciser unique vs total, le total est plus simple et plus parlant.

### Fait 4 — `recharts` n'est pas installé

`frontend/package.json:30-37` (dependencies) et `:38-58` (devDependencies) — `recharts` n'apparaît dans aucune des deux. L'AC #2 dit « renders the data as a chart per subject », l'agentic note de la story dit « Use a simple charting library (Recharts or Chart.js) ».

**Piège d'amorçage** : la story s16 doit ajouter `recharts` à `package.json` (et probablement un `pnpm install` pour mettre à jour `pnpm-lock.yaml`). Si la story s16 a lieu avant une story chart ailleurs, c'est la s16 qui paie le coût d'installation. Aucun impact si on accepte ce coût.

**Alternative** : Chart.js (`react-chartjs-2`). Plus mature, mais `<canvas>` plutôt que `<svg>`, ce qui complique l'accessibilité. Recharts est l'option par défaut du projet (`docs/architecture.md:36`).

### Fait 5 — Le cache 5 min n'a pas d'infra

`backend/requirements.txt` ne référence ni `redis` ni `cachetools` ni `fastapi-cache2`. Redis est listé dans `architecture.md:24` (stack) et `:371` (integration points) — mais pas comme dépendance Python.

Pour implémenter l'AC #4 (« The data is cached for 5 minutes »), trois options :
- (a) **Cache in-process** : un `dict[pseudo, tuple[float, DashboardData]]` avec un TTL vérifié à chaque appel. Suffit pour la POC et les tests (in-memory, déterministe). **Inconvénient** : pas partagé entre workers uvicorn. Pour la POC, OK.
- (b) **`fastapi-cache2` + backend in-memory** : ajoute une couche propre (`@cache(expire=300)`) sans tirer Redis. Standard FastAPI.
- (c) **Redis** : introduit une dépendance infra. **Hors-scope POC.**

**Recommandation** : (a) — un module `app/services/dashboard/cache.py` de 30 lignes, avec une invalidation sur la clé `(pseudo,)` (la story dit « per (pseudo, date) » mais la clé par date n'a pas de valeur — ce qui compte c'est que la clé change après une nouvelle tentative). On invalide via un **TTL** (5 min) plutôt qu'un événement, parce que l'AC dit explicitement « cached for 5 minutes ». Pour le test, on injecte un faux horloge ou on monkeypatche `time.monotonic`.

**Note** : l'AC dit aussi « invalidated on each new attempt ». Ces deux contraintes sont en tension. La lecture pragmatique : TTL 5 min **OU** invalidation explicite au premier attempt créé depuis le dernier cache — on fait **les deux** (invalidation explicite dans le router de l'attempt, TTL en filet de sécurité). Le plan doit le dire.

### Fait 6 — La route group frontend `(dashboard)/` n'existe pas encore

`frontend/app/` contient uniquement `(public)/` (s11a-s11c) et la racine `layout.tsx` + `globals.css`. La story note dit « `frontend/app/(dashboard)/eleve/dashboard/page.tsx` ». Cette route group doit être créée, avec :
- Un `layout.tsx` qui mount le `useAuthStore.hydrate()` et redirige vers `/login?next=...` si `!isAuthenticated` après hydration.
- Un `page.tsx` qui fetch `/api/dashboard/eleve` via `apiClient.get`, gère les états `loading` / `error` / `success`, et rend le chart Recharts.

**Piège d'amorçage** : c'est la première story à introduire le pattern `(dashboard)/` — le `layout.tsx`守卫 (auth guard) sera un nouveau template. Si la s17 (dashboard parent) ou la s18 (page exercices) arrive juste après, elles réutiliseront ce layout — c'est un investissement, pas du gaspillage.

**Question ouverte** : faut-il aussi un `(dashboard)/layout.tsx` à la racine du groupe, ou bien chaque page a son propre guard ? La convention Next.js veut un layout de groupe. **Recommandation** : un `(dashboard)/layout.tsx` unique, partagé par `eleve/`, `parent/`, `admin/` (même si la s16 ne crée que la branche `eleve/`).

### Fait 7 — Le `require_role(["eleve"])` est la granularité fine attendue

L'AC #6 demande qu'un élève A ne puisse pas voir le dashboard de B. C'est l'isolation cross-tenant : le `pseudo` du JWT est la seule source d'identité, l'endpoint filtre `WHERE student_pseudo = :pseudo` dans la query SQL.

**Parent** : le `require_role(["eleve"])` l'exclut. Si un parent hit `/api/dashboard/eleve` avec son JWT, il prend un 403 — c'est correct (c'est le dashboard de s17, `parent`).
**Admin** : par convention s15, l'admin bypass tout. À vérifier : la story ne le mentionne pas, mais l'ADR 005 § « admin bypass » le sous-entend. **Recommandation** : admin bypass sur ce endpoint (autoriser l'admin à requêter pour n'importe quel pseudo via un query param `?pseudo=...` ?). Décision à acter dans le plan, sinon l'admin ne peut pas voir le dashboard d'un élève depuis l'UI.

### Fait 8 — Aucun test cross-tenant pour `/api/dashboard/eleve` n'existe

C'est trivial : l'endpoint n'existe pas, donc les tests n'existent pas non plus. C'est un greenfield, pas un trou à signaler — juste à implémenter.

## Ancres d'implémentation

### Backend — fichiers à toucher

| Fichier | Changement attendu |
| --- | --- |
| `backend/app/api/dashboard/__init__.py` (new) | Marque le sous-domaine |
| `backend/app/api/dashboard/eleve.py` (new) | Router `GET /api/dashboard/eleve` avec `Depends(get_current_user)` + `require_role(["eleve"])` (admin bypass via helper s15), query SQL `GROUP BY subject` |
| `backend/app/api/dashboard/schemas.py` (new) | Pydantic `SubjectSummary`, `GlobalSummary`, `EleveDashboardResponse` |
| `backend/app/services/dashboard/__init__.py` (new) | Marque le service |
| `backend/app/services/dashboard/aggregator.py` (new) | `aggregate_eleven_dashboard(db, pseudo) -> EleveDashboardResponse` — pur, testable sans FastAPI |
| `backend/app/services/dashboard/cache.py` (new) | Cache in-process TTL 5 min, clé `dashboard:eleve:{pseudo}`, invalidation explicite via `invalidate(pseudo)` |
| `backend/app/api/exercises/router.py` (existing) | Ajouter `from app.services.dashboard.cache import invalidate_dashboard; invalidate_dashboard(pseudo=pseudo)` après chaque `Attempt` inséré |
| `backend/app/main.py` (existing) | `from app.api.dashboard.eleve import router as dashboard_eleve_router; app.include_router(dashboard_eleve_router, prefix="/api/dashboard", tags=["dashboard"])` |
| `backend/tests/api/dashboard/test_eleve.py` (new) | Tests AC #1, #5, #6 + admin bypass |

### Frontend — fichiers à toucher

| Fichier | Changement attendu |
| --- | --- |
| `frontend/package.json` (existing) | Ajouter `recharts: ^2.13.0` aux dependencies (commande `pnpm add recharts`) |
| `frontend/pnpm-lock.yaml` (existing) | Régénéré par pnpm |
| `frontend/app/(dashboard)/layout.tsx` (new) | Mount `useAuthStore.hydrate()` ; `useEffect` qui redirige vers `/login` si `!isAuthenticated` après hydration ; passe en props `{children}` |
| `frontend/app/(dashboard)/[locale]/layout.tsx` (new) | Wrapper `NextIntlClientProvider` pour le sous-groupe — calque sur `(public)/[locale]/layout.tsx` |
| `frontend/app/(dashboard)/[locale]/eleve/dashboard/page.tsx` (new) | Server Component qui fetch `/api/dashboard/eleve` via `apiClient.get`, rend `<DashboardClient>` |
| `frontend/app/(dashboard)/[locale]/eleve/dashboard/DashboardClient.tsx` (new) | `'use client'` ; gère `loading`/`error`/`success`, rend `<SubjectChart>` (Recharts BarChart) + `<SummaryCard>` |
| `frontend/app/(dashboard)/[locale]/eleve/dashboard/SubjectChart.tsx` (new) | Recharts responsive container, légende **en-dessous** à 360px (AC #3 — vérifier la prop `layout="vertical"` + `margin.top`/`bottom` ou un `ResponsiveContainer` + `Legend verticalAlign="bottom"`) |
| `frontend/messages/fr.json` (existing) | Clés `dashboard.eleve.title`, `dashboard.eleve.subtitle`, `dashboard.eleve.subjects.{maths,francais}`, `dashboard.eleve.empty`, `dashboard.eleve.error` |
| `frontend/messages/en.json` (existing) | Idem en |
| `frontend/e2e/dashboard.spec.ts` (new) | Tests Playwright (rendu, responsive 360px, a11y axe-core) |
| `frontend/lib/api/dashboard.ts` (new) | Wrapper typé `getEleveDashboard(): Promise<EleveDashboardResponse>` |

## APIs vérifiées (telles que le code les expose aujourd'hui)

### `GET /api/dashboard/eleve` (s16 — à créer)

```http
GET /api/dashboard/eleve
Authorization: Bearer <jwt>
```

- JWT `sub` = `pseudo`, `role` = `eleve` (ou `admin` bypass).
- Réponse 200 :
  ```json
  {
    "subjects": [
      {
        "name": "maths",
        "score_avg": 0.75,
        "exercises_count": 12,
        "last_activity_at": "2026-09-04T08:22:04Z"
      },
      {
        "name": "francais",
        "score_avg": 0.60,
        "exercises_count": 8,
        "last_activity_at": "2026-09-02T14:10:00Z"
      }
    ],
    "global": {
      "score_avg": 0.69,
      "exercises_count": 20,
      "last_activity_at": "2026-09-04T08:22:04Z"
    }
  }
  ```
- Erreur 401 : JWT manquant / invalide / expiré.
- Erreur 403 : rôle != eleve && != admin ; ou `pseudo` JWT != `pseudo` query (si on l'autorise via `?pseudo=...`).
- Erreur 500 : DB injoignable.

### `GET /api/dashboard/eleve?pseudo=alice` (admin bypass)

Si on autorise l'admin à requêter pour un autre pseudo, l'endpoint accepte `?pseudo=` et applique le helper `assert_jwt_pseudo_matches_or_403` de s15. Décision à acter dans le plan.

## Pièges et contraintes

1. **Prémisse « score » fausse (Fait 1)** : ne pas inventer un `score: float` sur `Attempt` à la volée. Décision à acter dans le plan (proxy `mean(is_success)` ou report à une story ultérieure).
2. **`recharts` à installer (Fait 4)** : ajoute une dépendance, un lock file change. C'est OK, mais le plan doit le dire explicitement (tâche dédiée).
3. **Cache TTL vs invalidation (Fait 5)** : les deux. Invalidation explicite sur nouvelle attempt + TTL filet de sécurité. Tester les deux chemins.
4. **Layout `(dashboard)/` à créer (Fait 6)** : c'est un investissement structurel. Le `layout.tsx` est partagé par les futures pages (s17, s18). Ne pas le s16-spécificiser (pas de `if (pathname === '/dashboard/eleve')`).
5. **Responsive 360px du chart (AC #3)** : Recharts `<Legend verticalAlign="bottom">` met la légende sous le chart, mais à 360px la chart elle-même devient illisible. Tester à 360px, pas juste à 768px.
6. **Admin bypass** : décision à acter — l'ADR 005 sous-entend bypass, mais la story ne le mentionne pas. Sans bypass explicite, l'admin ne peut pas voir le dashboard d'un élève en debug → friction ops.
7. **i18n** : toutes les chaînes via `useTranslations()`. Aucune string en dur. Le `card` « Taux de réussite : 75 % » est localisé.
8. **a11y** : Recharts utilise `<svg>`. Les `<text>` internes ne sont pas toujours lus par les screen readers. Pour un audit a11y propre, prévoir un `<table>` alternatif (data table) en plus du chart, ou un fallback ARIA. **Recommandation** : table sr-only, chart visible — pattern standard.
9. **Tests cross-tenant (AC #6)** : forger un JWT pour `bob` (helper déjà disponible via `create_access_token` en s13) et hit `/api/dashboard/eleve` avec ce JWT. Vérifier que la query SQL est filtrée par `student_pseudo = "bob"` — soit en lisant la réponse (qui doit être vide pour les matières de alice), soit en vérifiant qu'aucun `Document`/`Exercise`/`Attempt` de alice n'apparaît dans la sortie.
10. **Pas de Celery** : pas d'event « nouvel attempt » qui déclencherait un invalidation via message broker. L'invalidation est synchrone dans le router qui crée l'Attempt. C'est OK pour la POC, à challenger si l'app scale.

## Questions ouvertes (à confirmer au planning)

1. **`score_avg` — proxy `mean(is_success)` ou attendre un score numérique ?** Recommandation : proxy, label UI « Taux de réussite » pour ne pas tromper l'élève.
2. **`last_activity_at` — tentatives seulement, ou union avec uploads ?** Recommandation : tentatives seulement, plus simple, défendable. L'union est facile à ajouter.
3. **Admin bypass sur `?pseudo=...` ?** Recommandation : oui, pour le debug ops. Le helper s15 `assert_jwt_pseudo_matches_or_403` est en place.
4. **Cache invalidation : TTL only, ou TTL + invalidation explicite ?** Recommandation : les deux. TTL 5 min + `invalidate_dashboard(pseudo)` appelé depuis `app/api/exercises/router.py` à chaque `Attempt` inséré.
5. **Cache backend : in-process ou Redis ?** Recommandation : in-process pour la POC, Redis plus tard (s23+ ou un story ops). Inconvénient : pas partagé entre workers uvicorn — pour la POC mono-worker c'est OK.
6. **`exercises_count` = `COUNT(attempts)` ou `COUNT(DISTINCT exercise_id)` ?** Recommandation : `COUNT(attempts)` (= nombre de tentatives) — plus simple, plus parlant pour un élève.
7. **Table a11y en doublon du chart ?** Recommandation : oui, `<table>` sr-only avec les mêmes données que le chart. Pattern standard pour l'a11y Recharts.
8. **Recharts vs Chart.js ?** Recommandation : Recharts (architecture.md le liste, et la story le nomme en premier).

## Complexité re-scoring

| Source | Score | Justification |
| --- | --- | --- |
| `docs/stories.md` (déclaré) | 3 | « Aggregated SQL queries + chart rendering + responsive layout. » |
| Re-score après lecture du code | **4** | La story cumule : (a) greenfield backend sous-domaine, (b) greenfield frontend route group `(dashboard)/` + layout d'auth, (c) dépendance `recharts` à installer, (d) cache TTL + invalidation, (e) décision à acter sur le proxy `score_avg`, (f) i18n + a11y + responsive. Six axes distincts pour une seule story, dont trois greenfield. Le plan va probablement atterrir à 12-14 tâches. |

**Risque de blowup** : la s16 introduit trois socles (sous-domaine backend, route group frontend, lib `recharts`). Si l'implémentation est faite en TDD strict, on est à ~14 tâches — au-dessus de la cible « ≤ 10 tâches » du skill `ks-plan`.

## Split proposal (recommandé)

Si la s16 éclate, le cut le plus net est :

### s16a — Backend + cache + tests (sans UI)
- Endpoint `GET /api/dashboard/eleve` (router, schemas, service aggregator, cache in-process).
- 2 tests (auth OK, cross-tenant 403).
- Couvre les AC #1, #4, #5, #6.
- Touch : `app/api/dashboard/`, `app/services/dashboard/`, `app/api/exercises/router.py` (invalidation), `app/main.py` (include_router), `tests/api/dashboard/`.
- Plan estimé : 7-8 tâches. Complexité : 3.

### s16b — Frontend + recharts + layout (dashboard) + i18n + e2e
- `frontend/package.json` + `pnpm add recharts` + lock file.
- Route group `(dashboard)/` + layout auth guard.
- Page `/dashboard/eleve` + `<DashboardClient>` + `<SubjectChart>` (Recharts).
- Table sr-only pour a11y.
- i18n `dashboard.eleve.*` (fr + en).
- Tests Playwright (rendu, responsive 360px, axe-core).
- Touch : `frontend/app/(dashboard)/`, `frontend/messages/{fr,en}.json`, `frontend/lib/api/dashboard.ts`, `frontend/e2e/dashboard.spec.ts`.
- Couvre les AC #2, #3 + l'a11y/responsive/i18n qui sont des DoD.
- Plan estimé : 7-8 tâches. Complexité : 3.

**Pourquoi splitter** : la s16a et la s16b ont des owners différents (implémenteur backend vs implémenteur frontend), des fichiers disjoints, et la s16b peut être revue indépendamment (l'API est contract-locked par les tests de la s16a). Le seul couplage : la s16b consomme le contrat JSON fixé par les tests s16a.

**Pourquoi ne PAS splitter** : la s16 reste en dessous de 5 (la borne `4` que je donne est borderline, pas 5). Un seul commit, une seule review, un seul ship. C'est plus rapide et plus simple à diagnostiquer. **Recommandation finale** : ne pas splitter, mais **borner le plan à 11-12 tâches max** et accepter que c'est un sprint de 2-3 jours plutôt qu'un sprint d'un jour.

## Verdict

- **Prémisse** : partiellement fausse. La story demande `score_avg` mais la donnée n'existe pas. Trois options : proxy, attente, ou story de complément. À acter explicitement au planning.
- **Risques principaux** : (a) la décision sur le proxy de score, (b) la décision sur l'admin bypass, (c) la mise en place du layout `(dashboard)/` qui n'existe pas encore. Aucun n'est bloquant individuellement, mais leur cumul fait monter la complexité de 3 à 4.
- **Verdict complexité** : 4 (vs 3 déclaré). Borderline, pas de split obligatoire. **Split optionnel** si l'équipe préfère deux PRs plus petites.
- **Verdict split** : optionnel, recommandation = **garder en une story**, borner le plan à ≤ 12 tâches.
