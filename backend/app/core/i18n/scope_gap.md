Scope gap — s21-i18n-fr-en (T4 verified)

Endpoints checked via grep `message=` in `backend/app/api/`:
- `auth/router.py` — covered by s21 (register, login, refresh, logout)
- `documents/router.py` — hardcoded "Fichier trop volumineux." (not translated)
- `evaluations/router.py` — hardcoded "Fichier trop volumineux." (not translated)
- `users/router.py` — hardcoded messages (not translated)
- `exercises/` — no hardcoded message= found

Decision: these are out of scope for s21 (story AC covers auth + upload/evaluations contract check only). If future stories expand i18n to other routers, extend `messages_fr.json`/`en.json` and apply `get_message()` pattern.
