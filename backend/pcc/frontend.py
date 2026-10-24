"""Optional built frontend, sharing the existing API origin in packaged runs."""

from pathlib import Path

from fastapi import FastAPI
from starlette.staticfiles import StaticFiles


class FrontendFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        # Revalidate the document after an image update. Vite's hashed assets can
        # be cached, but a previous document must not reference deleted chunks.
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response


def mount_frontend(app: FastAPI, directory: str | None) -> None:
    if directory is None:
        return
    root = Path(directory)
    if not (root / 'index.html').is_file():
        raise RuntimeError('Built frontend is unavailable. Rebuild the PCC image.')
    # Registered API routes retain priority. Hash routing needs no catch-all
    # HTML fallback that might turn an unknown /api path into a successful page.
    app.mount('/', FrontendFiles(directory=root, html=True), name='frontend')
