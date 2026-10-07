from fastapi import FastAPI

from biodiv import __version__

app = FastAPI(
    title="Biodiversity Monitoring API",
    version=__version__,
    description="Invasive species presence and native-ecosystem impact.",
)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    """Liveness probe, also used by the keep-alive workflow to warm the service."""
    return {"status": "ok", "version": __version__}
