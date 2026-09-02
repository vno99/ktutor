"""Bcrypt password hashing wrapper (s12).

Bcrypt has a hard 72-octet limit on the input it accepts. We expose
two small functions that match the project's needs:

* :func:`hash_password` — produces a ``$2b$12$...`` string. The salt is
  random (a new salt per call) and the cost factor is hardcoded to 12
  (~250ms per hash, acceptable for a register flow).
* :func:`verify_password` — constant-time check that the plain text
  matches the stored hash. Malformed hashes return ``False`` instead
  of raising, so a corrupted row never produces a 500 in the router.

The 72-byte limit is enforced *upstream* by the Pydantic schema
(:class:`app.api.auth.schemas.RegisterRequest`) which keeps the
router free of low-level bcrypt errors. The wrapper still raises
``ValueError`` for empty / oversize inputs as a defence in depth — the
service can be reused from scripts or notebooks that bypass the
schema.
"""

from __future__ import annotations

import bcrypt

# Bcrypt refuses inputs longer than 72 bytes. The Pydantic schema
# (:class:`RegisterRequest`) already enforces this; the wrapper enforces
# it again so the function is safe to call from any code path.
BCRYPT_MAX_BYTES = 72

# Bcrypt cost factor. 12 is the convention for new code in 2026
# (~250ms per hash on a modern CPU) — enough to slow brute force
# attempts without making ``register`` feel slow. NOT a ``Settings``
# knob: keeping the value in one place makes audits easier (D5).
BCRYPT_ROUNDS = 12


def hash_password(plain: str) -> str:
    """Hash ``plain`` with bcrypt and return the encoded ``$2b$12$...`` string.

    Raises :class:`ValueError` for empty input or input whose UTF-8
    encoding exceeds :data:`BCRYPT_MAX_BYTES` bytes.
    """
    if not plain:
        raise ValueError("password must not be empty")
    encoded = plain.encode("utf-8")
    if len(encoded) > BCRYPT_MAX_BYTES:
        raise ValueError(f"password exceeds the 72-byte bcrypt limit ({len(encoded)} bytes)")
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return ``True`` iff ``plain`` matches ``hashed``.

    A malformed ``hashed`` (corrupted row, partial read, ...) returns
    ``False`` instead of raising so a downstream router never leaks a
    stack trace for a corrupt row.
    """
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
