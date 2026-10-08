"""Smoke-test the PUBLIC surface of a deployed REST API: local PostgREST or Supabase.

    python scripts/smoke_rest.py http://localhost:3000
    python scripts/smoke_rest.py https://YOUR-REF.supabase.co/rest/v1 --key YOUR_ANON_KEY

Run it after every deployment. It checks the two things that matter for a public dashboard: the
data the dashboard needs IS readable, and everything else is NOT (writes, internal functions,
PostGIS functions, partitions). Exit status is non-zero if any check fails.
"""

from __future__ import annotations

import argparse
import sys

import httpx

DENIED = {401, 403, 404}  # how PostgREST says "not for you", depending on what it can reveal


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("base", help="REST base URL, e.g. https://REF.supabase.co/rest/v1")
    p.add_argument("--key", default="", help="the PUBLIC anon key (never the service-role key)")
    args = p.parse_args()

    headers = {"Content-Type": "application/json"}
    if args.key:
        headers |= {"apikey": args.key, "Authorization": f"Bearer {args.key}"}
    client = httpx.Client(base_url=args.base.rstrip("/"), headers=headers, timeout=30)

    results: list[tuple[bool, str]] = []

    def check(ok: bool, what: str) -> None:
        results.append((ok, what))

    def readable(path: str, what: str, *, nonempty: bool = False) -> None:
        r = client.get(path)
        ok = r.status_code == 200 and (not nonempty or bool(r.json()))
        check(ok, f"can read {what} (HTTP {r.status_code})")

    def refused(method: str, path: str, what: str, **kw) -> None:
        r = client.request(method, path, **kw)
        check(r.status_code in DENIED, f"cannot {what} (HTTP {r.status_code})")

    # What the dashboard needs.
    readable("/zones?select=slug,name&order=id", "zones", nonempty=True)
    # A whole row INCLUDING its geometry. Converting geometry to JSON reads PostGIS's
    # spatial_ref_sys, which an over-eager lockdown once broke; selecting only plain columns
    # (as this script used to) could not notice.
    readable("/zones?limit=1", "a full zone row, geometry included", nonempty=True)
    readable("/species?select=scientific_name&limit=1", "species")
    readable("/alerts?select=*,zones(slug),species(scientific_name)&limit=1", "alerts with joins")
    readable("/mitigation_playbooks?select=method,source_quotes&limit=1", "mitigation playbooks")
    readable("/impact_findings?select=summary,certainty&limit=1", "impact findings")
    readable("/zone_reports?select=zone_id,computed_at&limit=1", "zone reports")
    readable("/source_health?select=name,items", "source health")
    readable("/model_versions?select=name,task,metrics&limit=1", "model versions")
    fc = client.get("/rpc/zones_geojson")
    check(fc.status_code == 200 and fc.json().get("type") == "FeatureCollection",
          "zones_geojson() returns a FeatureCollection")
    pts = client.get("/rpc/records_geojson", params={"p_kind": "invasive", "p_limit": 5})
    check(pts.status_code == 200 and pts.json().get("type") == "FeatureCollection",
          "records_geojson() returns a FeatureCollection")

    st = client.post("/rpc/storage_status", json={})
    body = st.json() if st.status_code == 200 else {}
    check(st.status_code == 200 and 0 < body.get("db_bytes", 0) and body.get("budget_bytes", 0) > 0,
          "storage_status() reports database size and budget")

    # What must not be possible.
    refused("POST", "/zones", "insert a zone", json={"slug": "x", "name": "x", "country": "IN"})
    refused("PATCH", "/species?id=gt.0", "update species", json={"common_name": "x"})
    refused("DELETE", "/alerts?id=gt.0", "delete alerts")
    refused("POST", "/zone_reports", "write a zone report", json={"zone_id": 1, "report": {}})
    refused("POST", "/rpc/refresh_rollups", "run refresh_rollups()", json={})
    refused("POST", "/rpc/ensure_detection_partition", "create partitions", json={"p_year": 2099})
    refused("POST", "/rpc/restrict_postgis_functions", "re-run the PostGIS lockdown", json={})
    refused("GET", "/rpc/postgis_full_version", "read PostGIS library versions")
    refused("GET", "/detections_2011?limit=1", "read a partition directly")
    refused("GET", "/schema_migrations?limit=1", "read migration bookkeeping")
    srs = client.get("/spatial_ref_sys", params={"select": "srid"})
    only_wgs84 = srs.status_code == 200 and {r["srid"] for r in srs.json()} <= {4326}
    check(only_wgs84, f"sees at most the WGS84 row of spatial_ref_sys (HTTP {srs.status_code})")

    width = max(len(w) for _, w in results)
    for ok, what in results:
        print(f"{'PASS' if ok else 'FAIL'}  {what:<{width}}")
    failed = sum(not ok for ok, _ in results)
    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
