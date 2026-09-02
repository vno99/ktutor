---
id: s12-creer-compte-eleve
title: Research — Créer un compte élève (pseudo + mot de passe)
date: 2026-09-02
status: ready
---

# Research — Story s12-creer-compte-eleve

## The five structuring facts

1. **Aucun `User` model n'existe** dans `backend/app/core/database/models.py:1-207` ; mais les modèles `Document`, `Exercise` et `Attempt` documentent en string form la FK `student_pseudo → users.pseudo` avec un commentaire récurrent « owned by story s12 (auth), FK intentionally deferred to s15 migration ». La table est **explicitement attendue** par le schéma, et le report à s15 est intentionnel.
2. **`bcrypt` n'est ni installé ni déclaré.** `python -c "import bcrypt"` → `ModuleNotFoundError`, `python -c "import passlib"` → `ModuleNotFoundError`. `backend/requirements.txt` ne mentionne ni `bcrypt`, ni `passlib`, ni `argon2`. Aucun module `core/auth/` n'existe (`ls backend/app/core/auth` → No such file or directory). Le wrapper de hash que la story attend dans `backend/app/core/auth/passwords.py` est à créer ET la dépendance à ajouter.
3. **La convention router est solide** : `app/api/<domaine>/router.py` + `schemas.py` + `factory.py` + `__init__.py` ; `APIRouter(prefix="/api/...", tags=[...])` ; injection par `Depends(...)` ; stubbabilité par `app.dependency_overrides[<dep>] = lambda: stub` (cf. `tests/api/conftest.py:101-108, 165-181`).
4. **`init_db()` est best-effort et idempotent** : `app/core/database/session.py:56-58` (`Base.metadata.create_all(bind=get_engine())`). Le lifespan FastAPI l'appelle dans un `try/except` (cf. `app/main.py:45-52`) — un `User` ajouté à `Base` sera donc créé en dev/CI sans Alembic, ce qui correspond à la convention s01-s10.
5. **L'ADR 005 a déjà tranché** le périmètre `register` : « `POST /api/auth/register` est public mais ne crée que des comptes `eleve` (cf. PRD § Identité : pas d'email, pas de nom réel). Les comptes `parent` et `admin` sont créés via `POST /api/users` (admin only, cf. story s13b). » (cf. `docs/decisions/005-auth-rs256-rbac.md:25`).

## Target story

**s12-creer-compte-eleve — Créer un compte élève (pseudo + mot de passe)**
As a **visiteur** I want **créer un compte élève en choisissant un pseudo et un mot de passe** so that **je puisse m'authentifier et accéder à mon espace**.

Acceptance criteria (tirés de `docs/stories.md`) :
- `POST /api/auth/register` accepte `{pseudo, password}` et renvoie 201 avec `{pseudo}` en cas de succès.
- Le mot de passe est hashé avec bcrypt (JAMAIS en clair).
- Le pseudo est unique (case-insensitive). Doublon → 409 avec un message clair.
- Le pseudo fait 3-32 chars, alphanumérique + underscore. Violation → 422.
- Le mot de passe fait ≥ 8 chars. Violation → 422.
- Une ligne `User` est créée en PostgreSQL avec `role='eleve'` par défaut.
- Un test couvre le happy path ET le cas duplicate-pseudo.

**Complexity annoncée : 2** — « Form + PostgreSQL insert + bcrypt hash + uniqueness check ».

## Current state of the code

- **Backend** : la chaîne `init_db() → Base.metadata.create_all → tables créées` est en place. Les tests modèles (`backend/tests/core/test_models.py:24-34`) reposent sur SQLite in-memory + `Base.metadata.create_all` — le pattern est directement réutilisable pour le modèle `User`.
- **Routers existants** : `api/chat/router.py` (s09) et `api/documents/router.py` (s10) — tous deux suivent la même grammaire (préfixe `/api/...`, schemas Pydantic à côté, factory.py à côté, dépendances injectées par `Depends`). Le `register` router se calque exactement sur ce gabarit.
- **CORS + lifespan** : déjà configurés dans `app/main.py:55-69`. Le `app.include_router(...)` est trivial à étendre.
- **Logging** : `loguru` configuré, autouse fixture `_isolated_loguru_sink` dans `backend/tests/conftest.py:28-55` qui buffer les logs en mémoire pour les assertions et isole les tests du sink de prod (UTF-8 / Windows).
- **Validation côté client** : ADR 011 impose `^[a-zA-Z0-9_]{3,32}$` sur le pseudo, aligné backend/frontend. La regex backend doit matcher exactement.
- **Aucun script de bootstrap admin** n'est encore en place — la story s15 l'attend (cf. ADR 005 § Consequences) mais ce n'est pas le scope ici.

## Anchor points

| Fichier | Rôle | État |
|---|---|---|
| `backend/app/api/auth/router.py` | `POST /api/auth/register` | **À créer** |
| `backend/app/api/auth/schemas.py` | `RegisterRequest`, `RegisterResponse`, `ErrorResponse` | **À créer** |
| `backend/app/core/auth/passwords.py` | wrapper `hash_password(plain) -> str` et `verify_password(plain, hashed) -> bool` | **À créer** (dépendance bcrypt à ajouter) |
| `backend/app/core/database/models.py` | ajout de la classe `User` (pseudo PK, password_hash, role, created_at) | **À modifier** |
| `backend/app/main.py:71-72` | `app.include_router(register_router)` | **À modifier** (une ligne) |
| `backend/requirements.txt` | ajout de la dépendance bcrypt (préférer `bcrypt>=4.0` direct, ou `passlib[bcrypt]`) | **À modifier** |
| `backend/tests/api/test_auth_register.py` | suite de tests (happy path, validation 422, duplicate 409) | **À créer** |
| `backend/tests/core/test_models.py` | ajouter `TestUserModel` (création, contrainte unicité case-insensitive) | **À modifier** |

## Verified APIs / functions

- `init_db()` — `app/core/database/session.py:56-58`. Crée toutes les tables du `Base.metadata`. Ajouté au lifespan FastAPI en best-effort.
- `get_db()` — `app/core/database/session.py:61-67`. Dépendance FastAPI : yield une `Session` SQLAlchemy, ferme en sortie de `with`.
- `Settings` — `app/core/config.py:10-162`. Pas de section « auth » encore. Si on veut paramétrer le coût bcrypt (`bcrypt_rounds`, défaut 12), c'est ici que ça va.
- `APIRouter(prefix="/api/auth", tags=["auth"])` — convention documentée dans `app/api/__init__.py:3` (« Each subpackage is a domain »).
- `HTTPException(status_code=..., detail=...)` — mappé à la réponse JSON `{detail: {...}}`. Le router `documents/router.py:117-127, 170-175` montre la convention : `detail` porte un dict sérialisé via un schema `UploadErrorResponse`. Le même pattern s'applique pour `register` : `RegisterErrorResponse(error: str, code: Literal["pseudo_taken", "weak_password", "invalid_pseudo"])`.
- `app.dependency_overrides[<dep>] = lambda: stub` — convention de stubbing test (`tests/api/conftest.py:101-108, 165-181`). Pour `register`, on n'a pas de service à stubber (l'opération est 100 % base + bcrypt), donc les tests sont plus simples : on tape directement la DB via la fixture `session` réutilisée.
- `Base.metadata.create_all(engine)` — pattern de test SQLite in-memory (`test_models.py:24-34`).
- `loguru` (`from loguru import logger`) + `logger.warning(...)` / `logger.info(...)` — pas d'inclusion de mot de passe, de hash, ni de token dans les logs (cf. AGENTS.md § Backend logging).

## Traps & constraints

1. **Dépendance bcrypt manquante.** `bcrypt>=4.0` n'est pas dans `requirements.txt`. Ajouter la dépendance est une pré-tâche de la story. Choix : `bcrypt` direct (idiomatique, populaire) ou `passlib[bcrypt]` (wrapper plus haut niveau, mais passlib a eu des problèmes de compat avec bcrypt 4.x — pin bcrypt<4 si on choisit passlib). **Recommandation : `bcrypt>=4.0` direct, plus simple et plus pérenne.**
2. **Bcrypt a une limite stricte de 72 octets** sur l'input. La story impose un minimum de 8 chars, pas de max. Piège documenté dans la story (« Bcrypt has a 72-byte input limit — pre-hash with SHA-256 if the password is long, or just enforce a 72-byte max. »). Décision à prendre au planning : (a) pré-hash SHA-256 → permet des mots de passe arbitrairement longs mais ajoute un module hashlib ; (b) max explicite 72 chars (Pydantic `max_length=72` + `bytes ≤ 72`) → simple, pragmatique, suffit pour le POC. **Recommandation : (b) — 72 chars max côté Pydantic, plus simple et plus auditable.**
3. **Unicité case-insensitive** : « Ali » et « ali » doivent collisionner. Pydantic `Field(...)` peut normaliser via un validator, et côté DB il faut soit une collation `case-insensitive`, soit un index fonctionnel `LOWER(pseudo) UNIQUE`. Le test_models.py actuel utilise SQLite sans collation particulière ; le check d'unicité doit s'appuyer sur `LOWER(pseudo)` au niveau SQLAlchemy (cf. `UniqueConstraint(func.lower(User.pseudo), name="uq_users_pseudo_lower")`).
4. **Le mot de passe ne doit jamais être loggé.** Même dans les messages d'erreur. La convention `loguru` est claire (AGENTS.md) ; le router `register` ne loggue QUE le `pseudo` et le `code` d'erreur (jamais le password ni le hash).
5. **Le endpoint est PUBLIC** : pas de JWT, pas d'auth. `Depends(get_db)` seulement. La s13 ajoutera le middleware RBAC.
6. **La table `users` ne doit PAS recevoir de FK sortantes** (pas de `parent_id` → `users.pseudo`, etc.) — c'est la s14. Le modèle `User` est strictement minimal : `pseudo` (PK), `password_hash`, `role`, `created_at`.
7. **Pas d'Alembic pour cette story.** La convention s01-s10 est d'ajouter le modèle dans `Base` et de laisser `init_db()` créer la table en dev/CI. Alembic sera câblé en s15 (FKs reportées). Cf. `models.py:56-72` (« FK intentionally deferred to s15 migration »).
8. **Pas de script de bootstrap admin** dans cette story. ADR 005 le mentionne mais le range en s15. Le `admin` n'est pas créable via `register` (qui ne crée que `eleve`), il sera créé par un script dédié.
9. **Tests d'isolation cross-tenant** : la story manipule la table `users` (création, lecture par pseudo) mais elle est à la frontière de l'isolation (l'identité elle-même). L'AC « test vérifie le happy path et le duplicate-pseudo » est explicite. Pas de test cross-tenant strict requis (il n'y a pas encore de « A peut lire les données de B » — c'est s15).
10. **i18n** : pas d'impact frontend sur cette story (le frontend public ne change pas). La s13 câblera le formulaire de login. Aucun message i18n à ajouter pour s12.

## Open questions

- **Coût bcrypt (rounds) ?** Défaut 12 = ~250ms par hash, acceptable pour un register. Si on le paramètre dans `Settings`, c'est une décision d'architecture (mineure) ; sinon on hardcode `12`. Le plan tranchera.
- **`max_length=72` (octets ou chars) ?** Bcrypt limite en **octets** UTF-8. Un mot de passe ASCII de 72 chars fait 72 octets ; un mot de passe avec accents peut faire moins de 72 chars mais plus d'octets. La règle propre : `len(password.encode("utf-8")) <= 72`. Le plan doit spécifier ça dans le validator Pydantic.
- **Pseudo normalization ?** Doit-on lowercaser à l'écriture (Ali → ali) ou seulement à la comparaison ? Si on lowercaser, on perd la casse d'origine (potentiellement importante pour l'affichage). Si on ne lowercaser pas, l'unicité doit reposer sur `LOWER()` en SQL. **Recommandation : préserver la casse, unicité via contrainte SQL `LOWER(pseudo)`**. Le test couvrira les deux (« Ali » et « ali » → 409 sur le 2e).
- **`User.role` enum ou string ?** L'ADR 005 dit « `"eleve" | "parent" | "admin"` ». Les enums Python sont déjà la convention (`models.py:18-50` pour `DocumentStatus`, `Subject`, `ExerciseType`). **Recommandation : `class UserRole(str, enum.Enum): ELEVE="eleve", PARENT="parent", ADMIN="admin"`, avec `default=UserRole.ELEVE`** (cohérence avec l'existant).
- **Le endpoint renvoie-t-il un JWT dès le register, ou juste un `{pseudo}` ?** La story dit « renvoie 201 avec `{pseudo}` » — c'est explicite. Le login (et donc le JWT) est en s13. Pas d'ambiguïté.

## Real complexity

**Score : 2, identique à la story. Aucun écart.**

Pourquoi : le périmètre est minimal, atomique, et bien découpé. Un endpoint, un modèle, un wrapper bcrypt, une suite de tests. La convention est en place, le schéma est en place, le bootstrap Alembic est différé (s15) ce qui retire la charge. Les pièges sont identifiés (bcrypt 72-byte, unicité case-insensitive, log hygiene) et chacun a une solution simple.

Pas de justification de split. Pas de signal qu'il faille découper plus fin.

## Split proposal

N/A. Score 2 confirmé après lecture du code.
