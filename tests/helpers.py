"""Test helpers shared across modules."""

import random
from datetime import UTC, datetime

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


class World:
    """Builds small, fully known datasets in a zone."""

    def __init__(self, conn, zone="bandipur"):
        self.conn = conn
        self.zone = zone
        self.zone_id = conn.execute("select id from zones where slug = %s", (zone,)).fetchone()[0]
        self.country = conn.execute("select country from zones where id = %s",
                                    (self.zone_id,)).fetchone()[0]
        self.source = conn.execute(
            "insert into sources (name, kind) values (%s, 'dataset') returning id",
            (f"test-{random.random()}",)).fetchone()[0]
        self.species_ids = {}
        self.n = 0

    def species(self, name, *, invasive=None, means=None):
        if name not in self.species_ids:
            sid = self.conn.execute(
                "insert into species (scientific_name, kingdom) "
                "values (%s, 'Plantae') returning id", (name,)).fetchone()[0]
            self.species_ids[name] = sid
            if invasive is not None or means:
                self.conn.execute(
                    "insert into invasive_status (species_id, country, is_invasive, "
                    "establishment_means) values (%s, %s, %s, %s)",
                    (sid, self.country, invasive, means or "Alien"))
        return self.species_ids[name]

    def observe(self, name, when, lon=76.5, lat=11.7):
        self.n += 1
        sid = self.species_ids[name]
        media = self.conn.execute(
            "insert into media_items (source_id, external_id, uri, captured_at, zone_id, geom) "
            "values (%s, %s, 'u', %s, %s, st_setsrid(st_makepoint(%s, %s), 4326)) returning id",
            (self.source, f"o{self.n}", when, self.zone_id, lon, lat)).fetchone()[0]
        self.conn.execute(
            "insert into detections (media_item_id, captured_at, species_id, confidence, geom, "
            "zone_id, origin) values (%s, %s, %s, 1.0, st_setsrid(st_makepoint(%s, %s), 4326), "
            "%s, 'observer')", (media, when, sid, lon, lat, self.zone_id))


def day(y, m=6, d=15):
    return datetime(y, m, d, tzinfo=UTC)
