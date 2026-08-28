# ADR 008 — DeepSeek-OCR-2 comme provider de vision pour l'OCR

- Status: accepted (supersede partiel de `docs/architecture.md` § Stack)
- Date: 2026-08-28
- Scope: story s01

## Context

Le PRD demande l'OCR de documents scannés et d'images dactylo/manuscrites.
`docs/architecture.md` § Stack mentionne **GPT-4o** ou **Gemini** comme
« LLM vision » pour cet usage. La planification s01 a relu cette liste et
l'a confrontée à trois critères :

1. **Coût** : GPT-4o et Gemini Vision sont payants à la requête. Pour un
   projet local et gratuit (CLAUDE.md), ce serait le seul poste de coût.
2. **Localité** : GPT-4o et Gemini sont des API distantes. Le PRD autorise
   un LLM par défaut local (Minimax-M3). L'OCR manuscrit n'a pas de raison
   d'être différent.
3. **Disponibilité d'un modèle open source viable** : DeepSeek-OCR-2 est un
   modèle de reconnaissance d'écriture / OCR publié librement, exécutable
   localement via un service HTTP (typiquement `http://localhost:8500`).

## Decision

Adopter **DeepSeek-OCR-2** comme provider de vision par défaut pour l'OCR
de s01. Le provider est sélectionné via `VISION_PROVIDER=deepseek-ocr-2`
dans `.env`, et l'URL par défaut est `DEEPSEEK_OCR_URL=http://localhost:8500`.

**Supersede** partiel de `docs/architecture.md` § Stack : la ligne
« Vision LLM : GPT-4o ou Gemini » est remplacée par « Vision LLM :
DeepSeek-OCR-2 (local par défaut), OpenAI GPT-4o ou Gemini en option ».
`VISION_PROVIDER` peut prendre les valeurs `deepseek-ocr-2 | openai | gemini`.

Le client OCR (`MultimodalOcr`) utilise `httpx` et parle directement au
service DeepSeek-OCR-2 via son endpoint `/v1/ocr`. Il n'utilise **pas**
`langchain_openai.ChatOpenAI` : la couche d'abstraction LangChain ne
justifie pas son overhead pour un appel HTTP ponctuel.

## Considered options

- **Option 1 — DeepSeek-OCR-2 (choix retenu)** : gratuit, local, conforme
  au principe « Minimax-M3 par défaut » du PRD. Mockable via
  `httpx.MockTransport` pour les tests unitaires (cf. `test_ocr.py`).

- **Option 2 — OpenAI GPT-4o** : excellent, mais payant. Réservé aux
  déploiements où le budget le permet. Sélection via `VISION_PROVIDER=openai`.

- **Option 3 — Google Gemini** : équivalent à GPT-4o en termes de coût.
  Pas d'avantage déterminant. Sélection via `VISION_PROVIDER=gemini`.

## Consequences

- **Coût nul** par défaut (modèle local, gratuit).
- **Latence locale** : ~50-200 ms par image (varie selon le GPU).
- **Dette architecturale connue** : DeepSeek-OCR-2 doit retourner du JSON
  strict pour que `MultimodalOcr` puisse le parser. Si la sortie réelle
  diverge, un LLM léger (Minimax-M3) pourra être utilisé comme étape de
  structuration. À vérifier en review d'intégration (cf. plan s01 §
  « The point everything turns on »).
- **Tests hermétiques** : `httpx.MockTransport` permet de tester le parsing
  et le retry sans appeler de service réel.
- **Migration facile** : changer `VISION_PROVIDER=openai` suffit à basculer
  sur GPT-4o. Une future story ajoutant un client GPT-4o créera un ADR qui
  supersedera celui-ci si nécessaire.
