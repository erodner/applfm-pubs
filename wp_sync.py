#!/usr/bin/env python3
"""Sync applfm.bib entries to the WordPress 'publication' post type on
foundationmodels.bht-berlin.de.

Setup
-----
Copy wp_credentials.example.json to wp_credentials.json (gitignored):
  { "base_url": "https://foundationmodels.bht-berlin.de",
    "username": "...", "password": "..." }
The account's normal WordPress login is used (the site blocks unauthenticated
REST and application passwords), via wp-login.php cookies + a REST nonce for
reading and the classic-editor post form for writing.

Usage
-----
  python3 wp_sync.py                 # dry run: report what would be created/updated
  python3 wp_sync.py --apply         # create missing entries as drafts
  python3 wp_sync.py --apply --publish   # create as published instead of drafts
  python3 wp_sync.py --apply --update    # also rewrite matched posts' fields

Data model of the publication post type (ACF)
---------------------------------------------
  title                          post_title
  venue                          acf text field 'published'
  raw BibTeX                     acf code field 'bibtex' (also used for matching:
                                 the bib key inside it identifies synced posts)
  authors                        acf repeater: Team (post_object -> team CPT) or
                                 External (name + institution)
  DOI / arXiv / PDF / link       acf repeater 'resources' (link fields)
  year, bibtex type, category    taxonomies publication-year,
                                 publication-bibtex-type, publication-category

Posts are matched by bib key in the bibtex field, then by normalized title.
Nothing is ever deleted; unmatched WordPress posts are reported.
"""
import argparse
import html
import http.cookiejar
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

# --- ACF field keys of the publication post type (discovered 2026-09-09) ---
F_PUBLISHED = "acf[field_69b30e1ec24c5]"                       # venue text
F_BIBTEX = "acf[field_69b30b0eca792]"                          # code editor
F_TAX_CATEGORY = "acf[field_69b308c077956]"                    # taxonomy select (term id)
F_TAX_YEAR = "acf[field_69b30a9758056]"                        # taxonomy select (term id)
F_TAX_TYPE = "acf[field_69b30aa158057]"                        # taxonomy select (term id)
AUTH_REP = "acf[field_69b30be47cff9]"                          # authors repeater
AUTH_CONN = "field_69b30cbd7cffe"                              # 'Team' | 'External'
AUTH_TEAM = "field_69b30c657cffc"                              # team post id
AUTH_EXT_GROUP = "field_69b30c9d7cffd"
AUTH_EXT_NAME = "field_69b30d0f7cfff"
AUTH_EXT_INST = "field_69b30d427d001"
RES_REP = "acf[field_69b30eb3b5814]"                           # resources repeater
RES_LINK = "field_69b31d481aa20"                               # link: title/url/target

TYPE_MAP = {"article": "Article", "inproceedings": "Conference Paper",
            "misc": "Preprint", "book": "Book", "phdthesis": "PhD Thesis"}

# Research-area category per bib group (fallback for future entries); the
# per-key map below covers every current non-preprint entry. Rules confirmed by
# the user 2026-09: M1 imprinting, M2 vision, M3 evaluation/robustness/fairness
# (incl. XAI, data quality, health-data quality), M4 NLP, R3 Löser medical NLP.
GROUP_CATEGORY = {
    "Boblan group (robotics, BHT Berlin)": "R1 - Robotics",
    "Höppner group (robotics, BHT Berlin)": "R1 - Robotics",
    "Reber group (BHT Berlin)": "R2 - Quantitative Biology",
    "Grohmann group (BHT Berlin)": "R2 - Quantitative Biology",
}
R2, R3 = "R2 - Quantitative Biology", "R3 - Predictive Medicine"
M1, M2 = "M1 - Continual Few-Shot Learning", "M2 - Vision and Motion"
M3, M4 = "M3 - Holistic Evaluation, Fairness, Robustness", "M4 - Adapting Text Embeddings"
KEY_CATEGORY = {
    "Koddenbrock2026Microtubule": R2, "Bangera2026Plasmodium": R2,
    "Biswas2025Density": R2, "Kletter2025Spindle": R2, "Kuhlmann2026TraF": R2,
    "Papaioannou2025SPONGE": R3, "Papaioannou2026ConformalPrediction": R3,
    "Roehr2024MIMIC": R3, "Grundmann2026CliniBench": R3,
    "Roehr2025WhereDoesItHurt": R3, "Roehr2026DeepICD": R3,
    "Figueroa2024LongTail": R3, "Fast2024AMEGA": R3,
    "Figueroa2025FinancialLiteracy": M4, "Mi2026Idiomaticity": M4,
    "Buchem2025Furhat": M4, "Kolomenko2026Embedding": M4,
    "Saha2025Pseudonymization": M4,
    "Knauer2025GrandmotherCells": M3, "Knauer2026ConceptTracer": M3,
    "Knauer2025DecisionTree": M3, "Knauer2026Physiotherapy": M3,
    "Westerhoff2025SCAM": M3, "Kostic2026SameMeaning": M3,
    "Chiaburu2025UncertaintyXAI": M3, "Jung2025MechDetect": M3,
    "Jung2025ErrorModels": M3, "Huang2024TinyChirp": M3,
    "Orynbay2025BloodSample": M3, "Nanevski2026SyntheticData": M3,
    "Nanevski2026FallRisk": M3, "Seibert2026AINCRA": M3,
    "Kozcuer2024Fairness": M3,
    "Singh2026SoilNet": M2,
    "Westerhoff2025WeightImprinting": M1,
    "Koddenbrock2026DeepBench": M3, "Reiss2025VisualICL": M2,
    "Harnischmacher2024BreastCancer": R3, "Schwarz2024FaultyLabels": M2,
    "Figueroa2025Comply": M4,
}


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def load_creds():
    if not CRED_FILE.exists():
        die(f"{CRED_FILE.name} not found - copy wp_credentials.example.json and fill it in.")
    c = json.loads(CRED_FILE.read_text())
    c["password"] = c.get("password") or c.get("app_password")
    for k in ("base_url", "username", "password"):
        if not c.get(k):
            die(f"{CRED_FILE.name} is missing '{k}'.")
    c["base_url"] = c["base_url"].rstrip("/")
    return c


class WPSession:
    def __init__(self, creds):
        self.base = creds["base_url"]
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))
        self.op.addheaders = [("User-Agent", "Mozilla/5.0 applfm-sync/1.0")]
        self._login(creds)
        self.nonce = self._get("/wp-admin/admin-ajax.php?action=rest-nonce").strip()

    def _login(self, creds):
        self._get("/wp-login.php")
        data = urllib.parse.urlencode({
            "log": creds["username"], "pwd": creds["password"],
            "wp-submit": "Log In", "redirect_to": self.base + "/wp-admin/",
            "testcookie": "1"}).encode()
        r = self.op.open(self.base + "/wp-login.php", data=data, timeout=45)
        if not any(k.name.startswith("wordpress_logged_in") for k in self.cj):
            die("WordPress login failed - check username/password in wp_credentials.json.")

    def _get(self, path):
        return self.op.open(self.base + path, timeout=60).read().decode(errors="replace")

    def rest(self, path, params=None):
        url = self.base + "/wp-json" + path + ("?" + urllib.parse.urlencode(params) if params else "")
        req = urllib.request.Request(url, headers={"X-WP-Nonce": self.nonce})
        return json.loads(self.op.open(req, timeout=60).read().decode())

    def rest_all(self, path, params=None):
        params = dict(params or {})
        params.setdefault("per_page", 100)
        out, page = [], 1
        while True:
            params["page"] = page
            try:
                items = self.rest(path, params)
            except urllib.error.HTTPError:
                break
            if not items:
                break
            out.extend(items)
            if len(items) < params["per_page"]:
                break
            page += 1
        return out

    def edit_form(self, post_id=None):
        """Fetch the classic-editor form; returns (post_id, hidden_fields)."""
        path = (f"/wp-admin/post.php?post={post_id}&action=edit" if post_id
                else "/wp-admin/post-new.php?post_type=publication")
        page = self._get(path)
        hidden = {}
        for m in re.finditer(r'<input[^>]*type=["\']hidden["\'][^>]*>', page):
            tag = m.group(0)
            nm = re.search(r'name=["\']([^"\']+)["\']', tag)
            vl = re.search(r'value=["\']([^"\']*)["\']', tag)
            if nm:
                hidden[html.unescape(nm.group(1))] = html.unescape(vl.group(1)) if vl else ""
        pid = hidden.get("post_ID") or (str(post_id) if post_id else None)
        if not pid:
            die(f"could not obtain post form for {path}")
        return int(pid), hidden, page

    def submit_post(self, hidden, fields, publish):
        payload = dict(hidden)
        # drop fields that would trigger unrelated actions
        for k in list(payload):
            if k.startswith(("meta-box-order", "wp-preview", "screen_id")):
                payload.pop(k)
        payload.update(fields)
        payload["action"] = "editpost"
        payload["post_type"] = "publication"
        if publish:
            payload["post_status"] = "publish"
            payload["publish"] = "Publish"
        else:
            payload["post_status"] = "draft"
            payload["save"] = "Save Draft"
        data = urllib.parse.urlencode(payload, doseq=True).encode()
        r = self.op.open(self.base + "/wp-admin/post.php", data=data, timeout=90)
        body = r.read().decode(errors="replace")
        if "post.php" not in r.url and "login" in r.url:
            die("session expired during submit")
        err = re.search(r'<div id="message"[^>]*class="[^"]*error[^"]*"[^>]*>(.*?)</div>', body, re.S)
        return r.url, (re.sub(r"<[^>]+>", " ", err.group(1)).strip() if err else None)


# ---------------------------------------------------------------- bib helpers
def norm_name(n):
    n = re.sub(r"\b(Prof|Dr|Ing|Jun|Sen)\.?\s*", "", n)
    n = n.replace("ß", "ss").lower()
    parts = [p for p in re.split(r"[\s.]+", n) if len(p) > 1]
    if len(parts) >= 2:
        return parts[0] + " " + parts[-1]
    return " ".join(parts)


def norm_title(t):
    return re.sub(r"\W", "", t.lower())[:80]


def plain_authors(raw):
    out = []
    for p in [x.strip() for x in delatex(raw).split(" and ")]:
        if "," in p:
            last, first = [x.strip() for x in p.split(",", 1)]
            out.append(f"{first} {last}")
        else:
            out.append(p)
    return out


def build_entries():
    groups = parse_bib(BIB.read_text())
    proofs = json.loads(PROOFS.read_text()) if PROOFS.exists() else {}
    entries = []
    for g in groups:
        for e in g["entries"]:
            f = e["fields"]
            proof = proofs.get(e["key"], {})
            entries.append({
                "key": e["key"], "type": e["type"].lower(),
                "title": delatex(f.get("title", e["key"])),
                "authors": plain_authors(f.get("author", "")),
                "year": f.get("year", ""),
                "venue": venue_of(e),
                "doi": f.get("doi", ""), "url": f.get("url", ""),
                "arxiv": arxiv_id(e) or "", "pdf": pdf_url(e, proof),
                "bibtex": e["raw"], "group": g["name"],
            })
    return entries


def author_rows(entry, team_index):
    fields = {}
    for i, name in enumerate(entry["authors"]):
        row = f"{AUTH_REP}[row-{i}]"
        tid = team_index.get(norm_name(name))
        if tid:
            fields[f"{row}[{AUTH_CONN}]"] = "Team"
            fields[f"{row}[{AUTH_TEAM}]"] = str(tid)
        else:
            fields[f"{row}[{AUTH_CONN}]"] = "External"
            fields[f"{row}[{AUTH_EXT_GROUP}][{AUTH_EXT_NAME}]"] = name
            fields[f"{row}[{AUTH_EXT_GROUP}][{AUTH_EXT_INST}]"] = ""
    return fields


def resource_rows(entry):
    links = []
    if entry["doi"]:
        links.append(("DOI", f"https://doi.org/{entry['doi']}"))
    if entry["arxiv"]:
        links.append(("arXiv", f"https://arxiv.org/abs/{entry['arxiv']}"))
    if entry["pdf"]:
        links.append(("PDF", entry["pdf"]))
    if entry["url"]:
        links.append(("Link", entry["url"]))
    fields = {}
    for i, (title, url) in enumerate(links):
        row = f"{RES_REP}[row-{i}][{RES_LINK}]"
        fields[f"{row}[title]"] = title
        fields[f"{row}[url]"] = url
        fields[f"{row}[target]"] = "_blank"
    return fields


def entry_fields(entry, team_index, terms):
    """terms: {"category": {name: id}, "year": {...}, "type": {...}}"""
    cat = KEY_CATEGORY.get(entry["key"]) or GROUP_CATEGORY.get(entry["group"], "")
    type_name = TYPE_MAP.get(entry["type"], "Article")
    fields = {
        "post_title": entry["title"],
        F_PUBLISHED: entry["venue"],
        F_BIBTEX: entry["bibtex"],
    }
    year_id = terms["year"].get(entry["year"])
    type_id = terms["type"].get(type_name)
    cat_id = terms["category"].get(cat) if cat else None
    if year_id:
        fields[F_TAX_YEAR] = str(year_id)
        fields["tax_input[publication-year][]"] = str(year_id)
    if type_id:
        fields[F_TAX_TYPE] = str(type_id)
        fields["tax_input[publication-bibtex-type][]"] = str(type_id)
    if cat_id:
        fields[F_TAX_CATEGORY] = str(cat_id)
        fields["tax_input[publication-category][]"] = str(cat_id)
    fields.update(author_rows(entry, team_index))
    fields.update(resource_rows(entry))
    return fields


# ---------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write to WordPress (default: dry run)")
    ap.add_argument("--update", action="store_true", help="with --apply: rewrite matched posts")
    ap.add_argument("--publish", action="store_true", help="create posts as published, not drafts")
    ap.add_argument("--limit", type=int, default=0, help="only process the first N creations (testing)")
    ap.add_argument("--include-preprints", action="store_true",
                    help="also sync @misc entries (preprints); skipped by default")
    ap.add_argument("--only", default="",
                    help="comma-separated bib keys: restrict create/update to these entries")
    args = ap.parse_args()

    wp = WPSession(load_creds())
    print("Logged in.")

    team = wp.rest_all("/wp/v2/team", {"status": "publish,draft"})
    team_index = {norm_name(re.sub(r"<[^>]+>", "", t["title"]["rendered"])): t["id"] for t in team}
    print(f"Team members: {len(team)}")

    terms = {}
    for label, tax in [("category", "publication-category"), ("year", "publication-year"),
                       ("type", "publication-bibtex-type")]:
        terms[label] = {html.unescape(t["name"]): t["id"] for t in wp.rest_all(f"/wp/v2/{tax}")}
    print(f"Taxonomy terms: {', '.join(f'{k}={len(v)}' for k, v in terms.items())}")

    existing = wp.rest_all("/wp/v2/publication",
                           {"context": "edit", "status": "publish,draft,pending,private"})
    print(f"Existing publications: {len(existing)}")

    # fetch each existing post's bibtex field to extract the bib key
    by_key, by_title, post_bibkey = {}, {}, {}
    for p in existing:
        title = re.sub(r"<[^>]+>", "", (p["title"].get("raw") or p["title"].get("rendered", "")))
        if title.strip():
            nt = norm_title(title)
            by_title.setdefault(nt, []).append(p)
        _, _, page = wp.edit_form(p["id"])
        m = re.search(r'name="' + re.escape(F_BIBTEX) + r'"[^>]*>(.*?)</textarea>', page, re.S)
        if m:
            km = re.search(r"@\w+\{\s*([^,\s]+)", html.unescape(m.group(1)))
            if km:
                post_bibkey[p["id"]] = km.group(1)
                by_key[km.group(1)] = p

    entries = build_entries()
    preprints = [e for e in entries if e["type"] == "misc"]
    if not args.include_preprints:
        entries = [e for e in entries if e["type"] != "misc"]
        for e in preprints:
            print(f"  SKIP (preprint) [{e['year']}] {e['title'][:64]}")
    if args.only:
        wanted = {k.strip() for k in args.only.split(",") if k.strip()}
        entries = [e for e in entries if e["key"] in wanted]
        print(f"--only filter: {len(entries)} entries")
    to_create, matched = [], []
    for e in entries:
        post = by_key.get(e["key"])
        if not post:
            cands = by_title.get(norm_title(e["title"]), [])
            post = cands[0] if cands else None
        (matched if post else to_create).append((e, post))

    matched_ids = {p["id"] for _, p in matched}
    orphans = [p for p in existing if p["id"] not in matched_ids]
    dupes = {t: ps for t, ps in by_title.items() if len(ps) > 1}

    print(f"\nBib entries: {len(entries)} | create: {len(to_create)} | "
          f"matched existing: {len(matched)} | on WP but not in bib: {len(orphans)}")
    for e, _ in to_create:
        cat = KEY_CATEGORY.get(e["key"]) or GROUP_CATEGORY.get(e["group"], "(no category)")
        ext = [a for a in e["authors"] if norm_name(a) not in team_index]
        print(f"  CREATE [{e['year']}] {e['title'][:64]}")
        print(f"         type={TYPE_MAP.get(e['type'])}  cat={cat}  "
              f"team-authors={len(e['authors']) - len(ext)}/{len(e['authors'])}")
    for e, p in matched:
        print(f"  MATCH  #{p['id']} [{p['status']}] {e['title'][:64]}")
    for p in orphans:
        t = re.sub(r"<[^>]+>", "", p["title"].get("rendered", "")) or "(empty title)"
        print(f"  ORPHAN #{p['id']} [{p['status']}] {t[:64]} (left untouched)")
    for t, ps in dupes.items():
        print(f"  DUPLICATE on WP: {', '.join('#' + str(p['id']) for p in ps)} share the same title")

    if not args.apply:
        print("\nDry run - nothing written. Use --apply to create"
              + (", --update to also rewrite matched posts" if matched else "") + ".")
        return

    creations = to_create[:args.limit] if args.limit else to_create
    for e, _ in creations:
        pid, hidden, _ = wp.edit_form()  # auto-draft via post-new.php
        fields = entry_fields(e, team_index, terms)
        url, err = wp.submit_post(hidden, fields, publish=args.publish)
        status = "publish" if args.publish else "draft"
        print(f"  created #{pid} ({status}) {e['title'][:60]}" + (f"  WARN: {err}" if err else ""))

    if args.update:
        for e, p in matched:
            pid, hidden, _ = wp.edit_form(p["id"])
            fields = entry_fields(e, team_index, terms)
            publish = p["status"] == "publish"
            url, err = wp.submit_post(hidden, fields, publish=publish)
            print(f"  updated #{pid} {e['title'][:60]}" + (f"  WARN: {err}" if err else ""))
    print("Done.")


if __name__ == "__main__":
    main()
