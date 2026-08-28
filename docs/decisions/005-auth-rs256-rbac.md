# ADR 005 — Authentification JWT RS256 + RBAC trois rôles

- Status: accepted
- Date: 2026-08-28
- Scope: framing

## Context

Le PRD exige une authentification JWT avec trois rôles (admin / parent / élève), identifiés par pseudo. Le CLAUDE.md précise RS256 (asymétrique) et un RBAC strict par endpoint.

Questions :

- Quel algorithme de signature ?
- Quels claims dans le JWT ?
- Comment représenter le RBAC ?
- Comment gérer la rotation des refresh tokens ?

## Decision

- **Algorithme** : RS256 (asymétrique, conforme à `CLAUDE.md`). La clé privée signe les access tokens et refresh tokens ; la clé publique vérifie. En local, les deux clés sont générées au démarrage et stockées sur disque (`./keys/jwt_private.pem`, `./keys/jwt_public.pem`, créés par un script `scripts/generate_jwt_keys.py` au premier lancement). En production, la clé privée serait dans un secret manager.
- **Claims** : `sub` (pseudo), `role` ("eleve" | "parent" | "admin"), `iat`, `exp`. Pas de `aud`/`iss` pour le POC (acceptable car local ; à ajouter en prod).
- **Access token** : durée 30 min (env `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`).
- **Refresh token** : durée 7 jours (env `JWT_REFRESH_TOKEN_EXPIRE_DAYS`). Stocké côté client. Rotation à chaque refresh (l'ancien est invalidé, le nouveau est émis). Blacklist en mémoire pour le POC, Redis en prod.
- **RBAC** : un middleware FastAPI (`Depends(get_current_user)`) extrait le `pseudo` et le `role` du JWT. Un décorateur `@require_role(["admin", "parent"])` vérifie le rôle avant l'appel de l'endpoint. Pour l'isolation multi-tenant, un second check compare le `pseudo` du JWT à celui de l'URL/body (lève 403 si mismatch, sauf pour `admin` qui peut impersoner).
- **Création de comptes** : `POST /api/auth/register` est public mais ne crée que des comptes `eleve` (cf. PRD § Identité : pas d'email, pas de nom réel). Les comptes `parent` et `admin` sont créés via `POST /api/users` (admin only, cf. story s13b).

## Considered options

- **HS256 (symétrique)** — rejeté par `CLAUDE.md` qui impose RS256. Le POC utilisait des API keys OpenAI, pas de JWT, donc ce n'est pas une régression.

- **RS256 avec clés dans le repo** — rejeté pour la prod, acceptable pour le POC. Les clés sont générées au premier lancement par un script et gitignorées.

- **Refresh token sans rotation** — rejeté. Sans rotation, un refresh token volé vit 7 jours. Avec rotation, la fenêtre est limitée au prochain refresh.

- **RBAC par permission granulaire (admin:users:create, parent:child:link, eleve:chat:send)** — rejeté pour le POC. Trois rôles × endpoints suffisent ; introduire des permissions granulaires ajoute du YAML et de la confusion. À considérer en prod.

- **Sessions serveur (cookie + Redis)** — rejeté. Le PRD mandate JWT. Le frontend utilise `localStorage` (acceptable pour le POC, à passer en cookie httpOnly pour la prod).

## Consequences

- **Sécurité conforme** : RS256, rotation, blacklist, RBAC strict. Pas de mot de passe en log, pas de token en log (cf. s23 trap).
- **Bootstrap admin** : le premier `admin` doit être créé sans authentification (sinon qui crée le premier admin ?). Une migration ou un script `scripts/bootstrap_admin.py` lit `ADMIN_PSEUDO` et `ADMIN_PASSWORD` du `.env` et crée l'admin si absent. Le script est idempotent.
- **Tests d'isolation** : pour chaque endpoint authentifié, un test vérifie qu'un JWT d'élève A ne peut pas accéder aux données de B. Cf. AGENTS.md § Définition of Done.
- **Le POC n'avait pas d'auth** : toute l'auth est nouvelle. Stories s12 à s15 la construisent par couches.
