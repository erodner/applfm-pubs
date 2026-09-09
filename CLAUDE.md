# CLAUDE.md

Curated BibTeX collection of publications acknowledging the DFG project **ApplFM** (Berlin Initiative for Applied Foundation Model Research, DFG Research Impulses FIP 12, Project-ID 528483508, 04/2024–03/2029).

## Files

- `applfm.bib` — the BibTeX entries; one comment above each entry quotes the paper's funding wording as verified.
- `README.md` — human-readable overview: inclusion criterion, paper list grouped by mention type, caveats.
- `generate_site.py` → `index.html` — GitHub Pages site (https://www.erodner.de/applfm-pubs/); regenerate after every bib change.
- `proofs.json` — per-entry funding quotations + verified PDF links, consumed by the generator.
- `wp_sync.py` — sync to the WordPress `publication` post type on foundationmodels.bht-berlin.de. Auth: normal WP login credentials in gitignored `wp_credentials.json` (`base_url`/`username`/`password` — application passwords are blocked by the site); cookie login via wp-login.php, REST (with nonce) for reading, classic-editor `post.php` form for writing (REST cannot write the ACF fields). The ACF field keys, category rules (`KEY_CATEGORY`), and type map are documented at the top of the script. Dry-run by default; `@misc` preprints are skipped; see README for all flags. Matching = bib key inside the post's `bibtex` ACF field, then normalized title.

## Inclusion criterion (strict)

A paper belongs here **only if its own full text** mentions the project — by name ("ApplFM" / "Berlin Initiative for Applied Foundation Model Research") or by DFG Project-ID 528483508 (often "Project-ID 528483508 - FIP 12"). Author affiliation or topical fit alone is NOT sufficient.

Consortium members to check for: Kristian Hildebrand, Ivo Boblan, Hannes Höppner, Alexander Löser, Erik Rodner, Felix Biessmann, Simone Reber, Elisabeth Grohmann, Felix Gers, Amy Siu. (Beware: a Scholar full-text match for a member's name plus the project ID can come from the paper's reference list citing their earlier work — confirm the person is an author or acknowledged, not merely cited.)

## Updating the collection

1. **Primary discovery tool: Google Scholar full-text search** for `"528483508"` (via browser — Scholar indexes acknowledgment sections that plain web search misses; in Sept 2026 this found 64 results across 7 pages vs. ~10 via web search). Also query `"ApplFM"` and `"Berlin Initiative for Applied Foundation Model"` for name-only mentions.
2. Verify candidates in the actual paper text where accessible: for arXiv papers, grep the **latest** version's HTML for `528483508` (acknowledgments are sometimes added in later versions — RamanBench v1 had none, v2 did). For paywalled venues (IEEE/Springer/Nature/ACM), the Scholar full-text match is the accepted evidence; tag `[scholar]`.
3. Get bibliographic metadata from the Crossref API (`api.crossref.org/works?query.bibliographic=...`) and the arXiv API — never guess author lists or venue details; Crossref author lists can be truncated in search results, so fetch the DOI record for the full list.
3b. **For every arXiv-only entry, check whether it has been formally published**: read the arXiv abs page's "Comments" and "Journal ref" fields (acceptance/venue info lands there) and run a Crossref title search. Upgrade published papers to `@article`/`@inproceedings` with the publisher metadata; record workshop acceptances in the `note` field. Re-check periodically — status changes (e.g., SCAM went from preprint to J. of Data-centric ML Research; the faulty-labels paper to WSCG 2025).
4. Add the entry to `applfm.bib` with a `[direct]`/`[scholar]` verification comment, update the tables in `README.md`, and bump the "last checked" date in both files.
5. Cross-check against the user's full publication list at github.com/erodner/publications (`paper.bib`) — any 2024+ paper there that is not in `applfm.bib` should have its full text checked for the project mention. Cross-checked 2026-09-09: of 11 such papers, 6 were full-text verified as NOT mentioning the project (LLMStructBench arXiv:2602.14743 and PMLBmini arXiv:2409.01635 have no DFG acknowledgment at all); 5 could not be verified (paywalled/inaccessible: Schulze2026, Grossmann2025, FuchsKittowski2025, Tenorio2025, Grimm2024/TIADE) but none match the project ID in Scholar's index.
6. **Abstract**: every entry carries a single-line `abstract = {...}` field (sanitized: no braces/backslashes). For new entries fetch it from the arXiv API, Crossref, or OpenAlex (`abstract_inverted_index` — reconstruct by position); publisher landing pages or proceedings PDFs as fallback. The displayed BibTeX (site + WordPress) omits the abstract line automatically.
7. **Proof**: add the entry to `proofs.json` — `{"quote": <verbatim funding sentence>, "source": <URL>, "pdf": <verified OA pdf url, optional>}`; quote `null` makes the site show the Scholar-index fallback. Extract the quote by fetching the accessible full text and taking the sentence around `528483508`. IEEE Xplore's per-paper funding metadata (`xplGlobal.document.metadata.fundingAgencies`, read via browser JS on the document page) can upgrade paywalled IEEE entries to `[direct]` — the ICARCV gait-library paper even carries grant number "528483508-FIP12" there.
8. After every bib change: `python3 generate_site.py` (commit `index.html` along), then `python3 wp_sync.py` → `--apply` (new entries need a `KEY_CATEGORY` mapping in wp_sync.py first). Use `--only <key>` for targeted fixes and `--update` to push field changes to existing posts.

## WordPress state (as of 2026-09-09)

47 published `publication` posts = the 47 non-preprint bib entries, matched via bib key in the `bibtex` ACF field. Trash contains the intentionally removed #558 (duplicate DeepBench) and #774 (empty post) — do not restore. The `team` CPT holds the consortium members for author linking; authors not in it become External rows (institution field mostly empty — fill manually in wp-admin if desired).

## Conventions

- Entry keys: `AuthorYearShortTitle` (e.g. `Koddenbrock2026DeepBench`).
- Special characters in author names use LaTeX escapes (`{\"o}`, `{\ss}`), not raw UTF-8.
- Prefer the published/camera-ready version's metadata (title, venue, pages, DOI) over arXiv/OpenReview submission metadata; note preprint IDs in the `note` field.
- TMLR papers are `@article` with `issn = {2835-8856}` and the OpenReview forum URL.
- **Never `git add -A` here** — stage named files only (a vim swap file of the credentials was once committed that way and forced a password rotation). `wp_credentials.json` and `*.swp` are gitignored, but stay explicit anyway.
