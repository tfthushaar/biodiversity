from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from strawberry.fastapi import GraphQLRouter

from biodiv import __version__
from biodiv.api.gql import get_context, schema
from biodiv.api.routes import router
from biodiv.core.settings import get_settings

app = FastAPI(
    title="Biodiversity Monitoring API",
    version=__version__,
    description=(
        "Invasive species presence and native-ecosystem impact. Read-only data, plus stateless "
        "photo analysis that stores nothing. The dashboard itself reads Supabase directly; this "
        "service adds the live demo, a GraphQL endpoint for researchers, and a REST view."
    ),
)

# Public and read-only, with no cookies or credentials, so any origin may call it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(GraphQLRouter(schema, context_getter=get_context), prefix="/graphql",
                   tags=["graphql"])


@app.api_route("/health", methods=["GET", "HEAD"], tags=["meta"])
def health() -> dict[str, str]:
    """Liveness probe, also used by the keep-alive workflow to warm the service.

    Answers HEAD as well as GET: uptime monitors usually ask for headers only, and a 405 there
    reads as "down" even though the service is fine.
    """
    return {"status": "ok", "version": __version__}
