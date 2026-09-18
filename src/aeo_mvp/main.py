"""CLI entrypoint."""

from __future__ import annotations


def run() -> None:
    import uvicorn

    uvicorn.run("aeo_mvp.api.app:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    run()
