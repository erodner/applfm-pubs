#!/usr/bin/env python3
"""Sync applfm.bib entries to the WordPress 'publication' post type.

Setup
-----
1. In WordPress, create an Application Password:
   wp-admin -> Users -> Profile -> Application Passwords -> add one (e.g. "applfm-sync").
2. Copy wp_credentials.example.json to wp_credentials.json (gitignored) and fill in:
   - base_url: https://foundationmodels.bht-berlin.de
   - username: your WP login name
   - app_password: the generated application password (spaces are fine)

Usage
-----
  python3 wp_sync.py --inspect       # discover the REST route and dump one existing
                                     # publication's JSON (use this first to see which
                                     # meta/ACF fields the post type has)
  python3 wp_sync.py                 # dry run: report what would be created/updated
  python3 wp_sync.py --apply         # create missing entries as drafts
  python3 wp_sync.py --apply --publish   # create as published instead of draft
  python3 wp_sync.py --apply --update    # also update already-synced posts in place

Behavior
--------
- Entries are matched to existing posts first by a hidden marker
  (<!-- applfm-key: ... --> in the post content), then by normalized title.
- Posts are never deleted; publications on WordPress that have no bib entry
  are only reported.
- The post body is a formatted citation (authors, venue, year, DOI/arXiv/PDF
  links) plus the raw BibTeX in a <pre> block. If --inspect reveals dedicated
  meta/ACF fields (e.g. authors, year, doi), map them in META_MAP below and
  they will be filled as well.
"""
import argparse
import base64
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from generate_site import arxiv_id, delatex, parse_bib, pdf_url, venue_of

HERE = Path(__file__).parent
CRED_FILE = HERE / "wp_credentials.json"
BIB = HERE / "applfm.bib"
PROOFS = HERE / "proofs.json"

REST_BASE_CANDIDATES = ["publication", "publications"]

# After running --inspect, map bib data to the post type's meta/ACF fields here,
# e.g. {"authors": "authors_text", "year": "year", "doi": "doi", "url": "external_url"}.
# Left side: one of authors|year|venue|doi|url|arxiv|pdf|bibtex ; right side: WP field name.
# Fields are written into the "acf" object if USE_ACF, else into "meta".
META_MAP: dict = {}
USE_ACF = False

MARKER = "applfm-key"


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def load_creds():
    if not CRED_FILE.exists():
        die(f"{CRED_FILE.name} not found. Copy wp_credentials.example.json to "
            f"{CRED_FILE.name} and fill in username + application password.")
    c = json.loads(CRED_FILE.read_text())
    for k in ("base_url", "username", "app_password"):
        if not c.get(k):
            die(f"{CRED_FILE.name} is missing '{k}'.")
    c["base_url"] = c["base_url"].rstrip("/")
    return c


class WP:
    def __init__(self, creds):
        self.base = creds["base_url"]
        token = base64.b64encode(
            f"{creds['username']}:{creds['app_password']}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {token}",
            "User-Agent": "applfm-wp-sync/1.0",
            "Accept": "application/json",
        }

    def req(self, method, path, payload=None, params=None):
        url = f"{self.base}/wp-json{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(payload).encode() if payload is not None else None
        headers = dict(self.headers)
        if data:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode()), dict(r.headers)
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:500]
            raise RuntimeError(f"{method} {url} -> HTTP {e.code}: {body}") from e

    def get_all(self, path, params=None):
        params = dict(params or {})
        params.setdefault("per_page", 100)
        page, out = 1, []
        while True:
            params["page"] = page
            try:
                items, headers = self.req("GET", path, params=params)
            except RuntimeError as e:
                if "rest_post_invalid_page_number" in str(e):
                    break
                raise
            if not isinstance(items, list) or not items:
                break
            out.extend(items)
            total_pages = int(headers.get("X-WP-TotalPages", "1"))
            if page >= total_pages:
                break
            page += 1
        return out


def discover_rest_base(wp):
    """Find the REST base of the publication post type."""
    try:
        types, _ = wp.req("GET", "/wp/v2/types")
    except RuntimeError as e:
        die(f"Cannot query post types ({e}).\nCheck the credentials, and that "
            "Application Passwords are enabled on the site.")
    for slug, t in types.items():
        if slug in ("publication", "publications") or \
           "publication" in (t.get("rest_base") or "") or \
           "publikation" in slug:
            rb = t.get("rest_base") or slug
            return rb, t
    # not in the types listing -> maybe not show_in_rest; probe candidates anyway
    for rb in REST_BASE_CANDIDATES:
        try:
            wp.req("GET", f"/wp/v2/{rb}", params={"per_page": 1})
            return rb, {}
        except RuntimeError:
            continue
    die("The 'publication' post type is not exposed in the REST API "
        "(show_in_rest is off). Ask the site admin to enable it, e.g. via:\n"
        "  add_filter('register_post_type_args', function($args, $type) {\n"
        "    if ($type === 'publication') { $args['show_in_rest'] = true; }\n"
        "    return $args; }, 10, 2);\n"
        "Then re-run this script.")


def norm_title(t):
    return re.sub(r"\W", "", t.lower())[:80]


def plain_authors(raw):
    parts = [p.strip() for p in delatex(raw).split(" and ")]
    out = []
    for p in parts:
        if "," in p:
            last, first = [x.strip() for x in p.split(",", 1)]
            out.append(f"{first} {last}")
        else:
            out.append(p)
    return ", ".join(out)


def build_entries():
    groups = parse_bib(BIB.read_text())
    proofs = json.loads(PROOFS.read_text()) if PROOFS.exists() else {}
    entries = []
    for g in groups:
        for e in g["entries"]:
            f = e["fields"]
            proof = proofs.get(e["key"], {})
            aid = arxiv_id(e)
            entries.append({
                "key": e["key"],
                "title": delatex(f.get("title", e["key"])),
                "authors": plain_authors(f.get("author", "")),
                "year": f.get("year", ""),
                "venue": venue_of(e),
                "doi": f.get("doi", ""),
                "url": f.get("url", ""),
                "arxiv": aid or "",
                "pdf": pdf_url(e, proof),
                "bibtex": e["raw"],
                "group": g["name"],
            })
    return entries


def render_content(entry):
    links = []
    if entry["doi"]:
        links.append(f'<a href="https://doi.org/{entry["doi"]}">DOI</a>')
    if entry["arxiv"]:
        links.append(f'<a href="https://arxiv.org/abs/{entry["arxiv"]}">arXiv</a>')
    if entry["url"]:
        links.append(f'<a href="{entry["url"]}">Link</a>')
    if entry["pdf"]:
        links.append(f'<a href="{entry["pdf"]}">PDF</a>')
    bib = entry["bibtex"].replace("<", "&lt;").replace(">", "&gt;")
    return (
        f"<!-- {MARKER}: {entry['key']} -->\n"
        f"<p>{entry['authors']}</p>\n"
        f"<p><em>{entry['venue']}</em>, {entry['year']}</p>\n"
        + (f"<p>{' &middot; '.join(links)}</p>\n" if links else "")
        + f"<details><summary>BibTeX</summary><pre>{bib}</pre></details>"
    )


def meta_payload(entry):
    if not META_MAP:
        return {}
    fields = {wp_field: entry.get(src, "") for src, wp_field in META_MAP.items()}
    return {"acf": fields} if USE_ACF else {"meta": fields}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inspect", action="store_true",
                    help="dump REST discovery info and one existing publication")
    ap.add_argument("--apply", action="store_true",
                    help="actually write to WordPress (default: dry run)")
    ap.add_argument("--update", action="store_true",
                    help="with --apply: update existing matched posts in place")
    ap.add_argument("--publish", action="store_true",
                    help="create new posts with status 'publish' instead of 'draft'")
    args = ap.parse_args()

    wp = WP(load_creds())
    rest_base, type_info = discover_rest_base(wp)
    print(f"Publication post type found; REST route: /wp/v2/{rest_base}")

    existing = wp.get_all(f"/wp/v2/{rest_base}",
                          params={"context": "edit", "status": "publish,draft,pending,private"})
    print(f"Existing publications on WordPress: {len(existing)}")

    if args.inspect:
        print("\n--- post type info ---")
        print(json.dumps(type_info, indent=1, ensure_ascii=False)[:1500])
        if existing:
            print("\n--- first existing publication (full JSON) ---")
            print(json.dumps(existing[0], indent=1, ensure_ascii=False)[:4000])
            print("\nUse this to fill META_MAP in wp_sync.py if the post type has "
                  "dedicated meta/ACF fields.")
        else:
            print("\nNo existing publications to inspect. Create one manually in "
                  "wp-admin and re-run --inspect to see its field structure.")
        return

    # index existing posts by marker key, then by normalized title
    by_key, by_title = {}, {}
    for p in existing:
        content = (p.get("content") or {}).get("raw") or (p.get("content") or {}).get("rendered", "")
        m = re.search(MARKER + r":\s*(\S+?)\s*-->", content)
        if m:
            by_key[m.group(1)] = p
        t = (p.get("title") or {}).get("raw") or (p.get("title") or {}).get("rendered", "")
        by_title[norm_title(re.sub(r"<[^>]+>", "", t))] = p

    entries = build_entries()
    to_create, to_update, unchanged = [], [], []
    for e in entries:
        post = by_key.get(e["key"]) or by_title.get(norm_title(e["title"]))
        if post is None:
            to_create.append(e)
        else:
            new_content = render_content(e)
            cur = (post.get("content") or {}).get("raw", "")
            (to_update if cur.strip() != new_content.strip() else unchanged).append((e, post))

    matched_ids = {p["id"] for _, p in to_update + unchanged}
    orphans = [p for p in existing if p["id"] not in matched_ids]

    print(f"\nBib entries: {len(entries)}  |  create: {len(to_create)}  |  "
          f"update: {len(to_update)}  |  unchanged: {len(unchanged)}  |  "
          f"on WP but not in bib: {len(orphans)}")
    for e in to_create:
        print(f"  CREATE  [{e['year']}] {e['title'][:70]}")
    for e, p in to_update:
        print(f"  UPDATE  #{p['id']} [{e['year']}] {e['title'][:70]}")
    for p in orphans:
        t = re.sub(r"<[^>]+>", "", (p.get("title") or {}).get("rendered", ""))
        print(f"  ORPHAN  #{p['id']} {t[:70]}  (left untouched)")

    if not args.apply:
        print("\nDry run - nothing written. Re-run with --apply to create"
              + (" and --update to update" if to_update else "") + ".")
        return

    status = "publish" if args.publish else "draft"
    for e in to_create:
        payload = {"title": e["title"], "content": render_content(e), "status": status}
        payload.update(meta_payload(e))
        created, _ = wp.req("POST", f"/wp/v2/{rest_base}", payload)
        print(f"  created #{created['id']} ({status}): {e['title'][:60]}")
    if args.update:
        for e, p in to_update:
            payload = {"title": e["title"], "content": render_content(e)}
            payload.update(meta_payload(e))
            wp.req("POST", f"/wp/v2/{rest_base}/{p['id']}", payload)
            print(f"  updated #{p['id']}: {e['title'][:60]}")
    elif to_update:
        print(f"  ({len(to_update)} posts differ; re-run with --update to update them)")
    print("Done.")


if __name__ == "__main__":
    main()
