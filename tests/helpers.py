"""Test helpers shared across modules."""

import httpx


def mock_gbif(respx_mock, matches, species=None):
    """Mock GBIF's species-match and species-lookup endpoints."""
    species = species or {}

    def match(request):
        name = request.url.params["scientificName"]
        return httpx.Response(200, json=matches.get(name, {"matchType": "NONE"}))

    def get_species(request):
        return httpx.Response(200, json=species[int(request.url.path.rsplit("/", 1)[1])])

    route = respx_mock.get("https://api.gbif.org/v1/species/match").mock(side_effect=match)
    respx_mock.get(url__regex=r"https://api\.gbif\.org/v1/species/\d+").mock(
        side_effect=get_species
    )
    return route


def exact(key, canonical, **extra):
    """A GBIF species-match response for an exact hit."""
    return {
        "usageKey": key, "canonicalName": canonical, "matchType": "EXACT", "confidence": 100,
        "kingdom": "Plantae", "rank": "SPECIES", **extra,
    }
