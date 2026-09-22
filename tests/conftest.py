import sys
from pathlib import Path

# The app modules live at the repo root (flat layout), so make them importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
