# CLAUDE.md

Curated BibTeX collection of publications acknowledging the DFG project **ApplFM** (Berlin Initiative for Applied Foundation Model Research, DFG Research Impulses FIP 12, Project-ID 528483508, 04/2024–03/2029).

## Files

- `applfm.bib` — the BibTeX entries; one comment above each entry quotes the paper's funding wording as verified.
- `README.md` — human-readable overview: inclusion criterion, paper list grouped by mention type, caveats.

## Inclusion criterion (strict)

A paper belongs here **only if its own full text** mentions the project — by name ("ApplFM" / "Berlin Initiative for Applied Foundation Model Research") or by DFG Project-ID 528483508 (often "Project-ID 528483508 - FIP 12"). Author affiliation or topical fit alone is NOT sufficient (e.g., RamanBench, arXiv 2605.02003, is deliberately excluded despite author overlap).

## Updating the collection

1. Search the web for new papers: query `"528483508"`, `"Project-ID 528483508"`, `"ApplFM" DFG`, and `"Berlin Initiative for Applied Foundation Model Research"`.
2. Verify each candidate's acknowledgment/funding section in the actual paper text (arXiv HTML version, publisher page, or PDF) before adding it — a search hit alone is not verification.
3. Add the entry to `applfm.bib` with a comment quoting the funding wording, update the table in `README.md`, and bump the "last checked" date in both files.

## Conventions

- Entry keys: `AuthorYearShortTitle` (e.g. `Koddenbrock2026DeepBench`).
- Special characters in author names use LaTeX escapes (`{\"o}`, `{\ss}`), not raw UTF-8.
- Prefer the published/camera-ready version's metadata (title, venue, pages, DOI) over arXiv/OpenReview submission metadata; note preprint IDs in the `note` field.
- TMLR papers are `@article` with `issn = {2835-8856}` and the OpenReview forum URL.
