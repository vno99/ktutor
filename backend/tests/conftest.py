"""Pytest configuration and shared fixtures for backend tests."""

from __future__ import annotations

import io
import sys
import uuid
from pathlib import Path

import pytest

# Ensure ``app`` is importable as a top-level package.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure each test gets a fresh settings cache (no env bleed-through)."""
    from app.core import config

    config.reset_settings()
    yield
    config.reset_settings()


# ---------------------------------------------------------------------------
# File fixtures
# ---------------------------------------------------------------------------

FIXTURE_DIR = BACKEND_ROOT / "tests" / "fixtures"


def _ensure_fixtures() -> Path:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    return FIXTURE_DIR


def make_sample_pdf(path: Path, pages: int = 3, page_text: str | None = None) -> Path:
    """Generate a small PDF with deterministic text using reportlab."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    for i in range(pages):
        body = page_text or (
            f"Cours de mathématiques — page {i + 1}\n"
            "La dérivée d'une fonction f en un point a est définie par :\n"
            "    f'(a) = lim (f(a+h) - f(a)) / h quand h -> 0\n"
            "Exemple: f(x) = x^2 -> f'(x) = 2x.\n"
        )
        # Naive wrap: write lines, splitting by \n
        x, y = 50, 780
        for line in body.splitlines():
            c.drawString(x, y, line)
            y -= 14
        c.showPage()
    c.save()
    return path


def make_typed_image(path: Path, text: str = "Bonjour le monde\nf(x) = x^2") -> Path:
    """Generate a PNG with typed text (mock 'OCR typed image' scenario)."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (640, 200), color="white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    draw.multiline_text((20, 40), text, fill="black", font=font)
    img.save(path)
    return path


def make_handwritten_image(path: Path, text: str = "Exercice: 2 + 3 = ?") -> Path:
    """Generate a PNG that looks like a handwritten scan.

    We simulate by using a cursive-like font and a slightly textured
    background. The OCR pipeline does not actually need to recognise this
    text in unit tests — it is here to exercise the file-type detection
    and the contract.
    """
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (640, 200), color=(245, 240, 220))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans-Oblique.ttf", 28)
    except OSError:
        font = ImageFont.load_default()
    draw.multiline_text((20, 60), text, fill=(20, 30, 80), font=font)
    img.save(path)
    return path


def make_oversized_file(path: Path, size_mb: int = 25) -> Path:
    """Write ``size_mb`` of zero bytes to ``path``."""
    path.write_bytes(b"\0" * (size_mb * 1024 * 1024))
    return path


@pytest.fixture(scope="session")
def sample_pdf_path() -> Path:
    _ensure_fixtures()
    path = FIXTURE_DIR / "sample_cours.pdf"
    if not path.exists():
        make_sample_pdf(path)
    return path


@pytest.fixture(scope="session")
def typed_image_path() -> Path:
    _ensure_fixtures()
    path = FIXTURE_DIR / "sample_typed.png"
    if not path.exists():
        make_typed_image(path)
    return path


@pytest.fixture(scope="session")
def handwritten_image_path() -> Path:
    _ensure_fixtures()
    path = FIXTURE_DIR / "sample_handwritten.png"
    if not path.exists():
        make_handwritten_image(path)
    return path


@pytest.fixture()
def tmp_upload(tmp_path: Path) -> Path:
    """A scratch directory for per-test files (huge file, invalid ext, etc.)."""
    return tmp_path


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def fixed_document_id() -> uuid.UUID:
    """A deterministic document id for assertions."""
    return uuid.UUID("12345678-1234-5678-1234-567812345678")
