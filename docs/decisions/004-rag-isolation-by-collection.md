# ADR 004 — Isolation multi-tenant RAG par collection ChromaDB nommée

- Status: accepted
- Date: 2026-08-28
- Scope: framing

## Context

Le PRD exige une isolation multi-tenant stricte : un élève A ne doit JAMAIS voir les documents d'un élève B, ni dans ChromaDB, ni dans PostgreSQL, ni dans MinIO, ni via le JWT. C'est une exigence de sécurité et un test d'isolation est requis par story API (cf. `AGENTS.md` § Définition of Done).

Pour ChromaDB, plusieurs options d'isolation existent :

1. **Une collection par (matière × élève)** : `rag_maths_ali`, `rag_francais_ali`, etc.
2. **Une collection unique, filtrée par `metadata.student_pseudo`** dans chaque requête.
3. **Une collection par matière, partagée, mais chunks ré-écrits avec un identifiant d'élève en préfixe** (obfuscation).
4. **Une instance ChromaDB par élève** (overkill).

## Decision

Adopter l'**option 1 : une collection par (matière × élève)**, convention de nommage `rag_<subject>_<pseudo>`.

Implémentation : une factory `get_chroma_collection(subject: str, pseudo: str) -> chromadb.Collection` qui :
- Valide le format du `pseudo` (alphanumeric + underscore, 3-32 chars, cf. s12).
- Construit le nom `rag_<subject>_<pseudo>`.
- Appelle `client.get_or_create_collection(name=...)`.
- Le `client` est `chromadb.PersistentClient` avec `path` depuis `CHROMA_PERSIST_DIRECTORY`.

Le superviseur LangGraph (ADR 003) reçoit le `pseudo` depuis le JWT, jamais depuis le body ou l'URL. Le `pseudo` est utilisé pour construire le nom de collection et passé à l'agent spécialisé, qui n'a aucun autre moyen d'accéder à une autre collection.

## Considered options

- **Option 1 — collection par (matière × élève) (choix retenu)** : isolation native de ChromaDB (la collection est cloisonnée physiquement). Pas de risque d'oubli de filtre `where`. Le coût est de gérer N collections (mais ChromaDB scale sans problème à des milliers de collections). Le test d'isolation est trivial : `client.get_collection("rag_maths_a")` ne peut pas retourner les chunks de `rag_maths_b` car ce sont deux collections distinctes.

- **Option 2 — collection unique + filtre `where`** : plus économe en metadata storage, mais le filtre `where` est oublliable. Un seul oubli dans un endpoint et l'isolation saute. Rejeté pour des raisons de sécurité.

- **Option 3 — obfuscation par préfixe** : ne tient pas — ChromaDB n'a pas de notion d'ACL par préfixe de texte. C'est de la sécurité par l'obscurité, rejetée.

- **Option 4 — instance ChromaDB par élève** : isolation maximale, mais overhead prohibitif (une instance = un process = des ressources). Rejeté.

## Consequences

- **Sécurité forte par défaut** : impossible d'accéder à la mauvaise collection sans changer le `pseudo` (et le `pseudo` vient du JWT).
- **Nommage déterministe** : `rag_maths_ali` se reconstruit à partir de `(maths, ali)`. Permet de lister les collections d'un élève, de nettoyer, de migrer.
- **Coût metadata** : ChromaDB stocke le nom de collection en interne. N collections = N entrées metadata. À 1000 élèves × 2 matières = 2000 collections, c'est gérable.
- **Migration / backup** : pour backuper un élève, on itère sur les collections `rag_*_<pseudo>` et on les exporte. Convention stable = opération triviale.
- **Test obligatoire par story API** : cf. `AGENTS.md` § Définition of Done.
