"""Generate the RS256 keypair used by ``app.core.auth.jwt`` (s13).

The script is **idempotent** : if both ``keys/jwt_private.pem`` and
``keys/jwt_public.pem`` already exist on disk, the script exits 0
without overwriting them. The operator can force regeneration by
deleting the files first.

The keys are produced in the **repository root** (not inside
``backend/``) because the runtime code (``Settings.jwt_*_key_path``)
reads them with a path relative to the working directory. For the
typical ``uvicorn`` invocation from ``backend/`` this is
``./keys/jwt_*.pem``; for a Docker compose the operator can mount
the keys at a stable path and update the env accordingly.

Security notes (s13 traps):

* The private key is **NEVER** encrypted. The POC runs in a local
  environment without KMS / secret-manager access. Production
  should mount the private key from a secret manager and protect
  it with a passphrase (cf. ADR 005 § Considered options).
* Both files are written with ``0600`` permissions on POSIX. On
  Windows the chmod is a no-op (the file is created with the
  current user's ACL), which is acceptable for a local dev box.
* The script never logs the private key bytes (only the path).
"""

from __future__ import annotations

import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# Repository root is the parent of ``backend/`` when the script is
# invoked as ``python backend/scripts/generate_jwt_keys.py``. We
# anchor on the file location to be robust to the current working
# directory of the caller.
BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent

PRIVATE_KEY_PATH = REPO_ROOT / "keys" / "jwt_private.pem"
PUBLIC_KEY_PATH = REPO_ROOT / "keys" / "jwt_public.pem"

KEY_SIZE = 2048
PUBLIC_EXPONENT = 65537


def _keypair_exists() -> bool:
    """Return ``True`` iff both PEM files are present and non-empty."""
    return (
        PRIVATE_KEY_PATH.is_file()
        and PUBLIC_KEY_PATH.is_file()
        and PRIVATE_KEY_PATH.stat().st_size > 0
        and PUBLIC_KEY_PATH.stat().st_size > 0
    )


def generate_keypair() -> None:
    """Generate a fresh RSA 2048 keypair and write it to the canonical paths.

    The private key is serialized in PKCS8 PEM (the modern format
    recommended by the ``cryptography`` docs). The public key is
    serialized as ``SubjectPublicKeyInfo`` PEM. The script logs the
    output paths only; the key material itself is never written to
    a log line.
    """
    PRIVATE_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)

    private_key = rsa.generate_private_key(
        public_exponent=PUBLIC_EXPONENT,
        key_size=KEY_SIZE,
    )
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    PRIVATE_KEY_PATH.write_bytes(private_pem)
    PUBLIC_KEY_PATH.write_bytes(public_pem)

    # Restrict to the owner on POSIX. ``chmod`` is a no-op on Windows
    # but does not raise — the file is created with the current
    # user's ACL.
    try:
        PRIVATE_KEY_PATH.chmod(0o600)
        PUBLIC_KEY_PATH.chmod(0o644)
    except (OSError, NotImplementedError):
        # Windows ACL or filesystem without POSIX mode bits.
        pass

    print(f"jwt_keys: private={PRIVATE_KEY_PATH}", file=sys.stderr)
    print(f"jwt_keys: public={PUBLIC_KEY_PATH}", file=sys.stderr)


def main() -> int:
    if _keypair_exists():
        # Idempotent: the keys are already on disk, nothing to do.
        print("jwt_keys: existing keypair found, skipping", file=sys.stderr)
        return 0
    generate_keypair()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
