# CLAUDE.md

Curated BibTeX collection of publications acknowledging the DFG project **ApplFM** (Berlin Initiative for Applied Foundation Model Research, DFG Research Impulses FIP 12, Project-ID 528483508, 04/2024–03/2029).

## Files

- `applfm.bib` — the BibTeX entries; one comment above each entry quotes the paper's funding wording as verified.
- `README.md` — human-readable overview: inclusion criterion, paper list grouped by mention type, caveats.

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

## Conventions

- Entry keys: `AuthorYearShortTitle` (e.g. `Koddenbrock2026DeepBench`).
- Special characters in author names use LaTeX escapes (`{\"o}`, `{\ss}`), not raw UTF-8.
- Prefer the published/camera-ready version's metadata (title, venue, pages, DOI) over arXiv/OpenReview submission metadata; note preprint IDs in the `note` field.
- TMLR papers are `@article` with `issn = {2835-8856}` and the OpenReview forum URL.
