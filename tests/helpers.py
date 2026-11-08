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


def give_paper(conn, species_id):
    """A verified finding about a species. Its study design is 'modelled', which no alert treats as
    documented harm, so giving a species a paper never changes an alert's severity."""
    conn.execute(
        "insert into impact_findings (invasive_species_id, finding_type, affected, summary, "
        "certainty, region_note, source_quotes, citation_text, citation_url, citation_doi, "
        "citation_year, citation_journal, verified_on) values (%s, 'impact', 'test', 'test', "
        "'modelled', 'test', '[\"a quote long enough to count\"]', 'A paper', "
        "'https://doi.org/10.1234/paper', '10.1234/paper', 2021, 'Journal', '2026-01-01') "
        "on conflict do nothing", (species_id,))


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

    def add_source(self, name):
        return self.conn.execute(
            "insert into sources (name, kind) values (%s, 'dataset') returning id", (name,)
        ).fetchone()[0]

    def species(self, name, *, invasive=None, means=None, kingdom="Plantae", paper=None):
        """A species in the zone. An invasive one gets a verified paper by default, because the
        platform records an invasive species only when a paper backs it; pass paper=False for one
        that has none."""
        if name not in self.species_ids:
            sid = self.conn.execute(
                "insert into species (scientific_name, kingdom) "
                "values (%s, %s) returning id", (name, kingdom)).fetchone()[0]
            self.species_ids[name] = sid
            if invasive is not None or means:
                self.conn.execute(
                    "insert into invasive_status (species_id, country, is_invasive, "
                    "establishment_means) values (%s, %s, %s, %s)",
                    (sid, self.country, invasive, means or "Alien"))
            if paper is True or (invasive and paper is not False):
                give_paper(self.conn, sid)
        return self.species_ids[name]

    def add_paper(self, name):
        give_paper(self.conn, self.species_ids[name])

    def observe(self, name, when, lon=76.5, lat=11.7, source=None):
        self.n += 1
        sid = self.species_ids[name]
        media = self.conn.execute(
            "insert into media_items (source_id, external_id, uri, captured_at, zone_id, geom) "
            "values (%s, %s, 'u', %s, %s, st_setsrid(st_makepoint(%s, %s), 4326)) returning id",
            (source or self.source, f"o{self.n}", when, self.zone_id, lon, lat)).fetchone()[0]
        self.conn.execute(
            "insert into detections (media_item_id, captured_at, species_id, confidence, geom, "
            "zone_id, origin) values (%s, %s, %s, 1.0, st_setsrid(st_makepoint(%s, %s), 4326), "
            "%s, 'observer')", (media, when, sid, lon, lat, self.zone_id))


def day(y, m=6, d=15):
    return datetime(y, m, d, tzinfo=UTC)


def paper(**over):
    """A cited paper as the knowledge file spells it: a journal article with a DOI."""
    source = {
        "doi": "10.1234/example.2021.001", "title": "Invasive plants in tropical forests",
        "authors": "Author, A.B.", "year": 2021, "journal": "Journal of Examples",
        "volume": "12", "pages": "1-10",
    }
    return {**source, **over}


def knowledge_file(*, playbooks=(), findings=(), verified_on="2026-10-07", **sources):
    """A small valid knowledge file. Rows cite the source named "s" unless they say otherwise."""
    return {
        "_policy": {"min_year": 2016, "blocked_venues": ["EDIS"]},
        "verified_on": verified_on,
        "sources": {"s": paper(), **sources},
        "playbooks": list(playbooks),
        "impact_findings": list(findings),
    }


def finding_row(species="Lantana camara", zone=None, **over):
    return {
        "species": species, "zone": zone, "finding_type": "impact", "affected": "forest plants",
        "summary": "Fewer plant species where it grows.", "certainty": "observational",
        "region_note": "A forest in southern India.", "source": "s",
        "quotes": ["a quote long enough to count as evidence here"], **over,
    }


def playbook_row(species="Lantana camara", **over):
    return {
        "species": species, "method": "mechanical", "summary": "Pulling it up.",
        "study_design": "experimental", "region_note": "A forest in southern India.",
        "source": "s", "quotes": ["Hand pulling is suitable for small areas of infestation."],
        **over,
    }
