"""Pytest path bootstrap for ui/gradio package imports.

Critical: pytest may insert ``.../ui`` onto ``sys.path`` because this tree lives
under ``ui/gradio/``. That would make ``import gradio`` resolve to *this* folder
instead of the third-party Gradio package. Strip that entry and clear a bad
``gradio`` module cache before tests import the real library.
"""

from __future__ import annotations

import sys
from pathlib import Path

UI_ROOT = Path(__file__).resolve().parents[1]
TESTS_ROOT = Path(__file__).resolve().parent
REPO_UI = UI_ROOT.parent  # .../ui


def _unshadow_gradio() -> None:
    cleaned: list[str] = []
    for entry in sys.path:
        try:
            resolved = str(Path(entry).resolve())
        except Exception:  # noqa: BLE001
            cleaned.append(entry)
            continue
        if resolved == str(REPO_UI.resolve()):
            continue
        cleaned.append(entry)
    sys.path[:] = cleaned

    mod = sys.modules.get("gradio")
    if mod is not None:
        f = str(getattr(mod, "__file__", "") or "")
        if f.endswith("/ui/gradio/__init__.py") or "/ui/gradio/" in f and "site-packages" not in f:
            del sys.modules["gradio"]
            for key in list(sys.modules):
                if key.startswith("gradio."):
                    del sys.modules[key]


_unshadow_gradio()

for path in (str(UI_ROOT), str(TESTS_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)
