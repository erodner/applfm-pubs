#!/usr/bin/env python3
"""Generate index.html (GitHub Pages) from applfm.bib.

Usage: python3 generate_site.py
"""
import html
import json
import re
from datetime import date
from pathlib import Path

BIB = Path(__file__).parent / "applfm.bib"
OUT = Path(__file__).parent / "index.html"
PROOFS = Path(__file__).parent / "proofs.json"
SCHOLAR_URL = "https://scholar.google.com/scholar?q=%22528483508%22"

PIS = [
    "Kristian Hildebrand", "Ivo Boblan", "Hannes Höppner", "Alexander Löser",
    "Erik Rodner", "Felix Biessmann", "Felix Bießmann", "Simone Reber",
    "Elisabeth Grohmann", "Felix Gers", "Felix A. Gers", "Felix Alexander Gers",
    "Amy Siu",
]

LATEX = {
    r'{\"o}': "ö", r'{\"a}': "ä", r'{\"u}': "ü", r'{\"O}': "Ö", r'{\"A}': "Ä",
    r'{\"U}': "Ü", r"{\ss}": "ß", r"{\'i}": "í", r"{\'e}": "é", r"{\'a}": "á",
    r"{\'u}": "ú", r"{\'c}": "ć", r"{\~n}": "ñ", r"{\'o}": "ó", r"``": "“",
    r"''": "”", r"--": "–", r"\&": "&",
}


def delatex(s: str) -> str:
    for k, v in LATEX.items():
        s = s.replace(k, v)
    s = re.sub(r"[{}]", "", s)
    return s.strip()


def parse_bib(text: str):
    """Parse the bib file, keeping section headers and per-entry comments."""
    groups = []  # list of {"name": str, "entries": [...]}
    current = None
    lines = text.splitlines()
    i = 0
    pending_comment = []
    while i < len(lines):
        line = lines[i]
        m = re.match(r"% -+$", line.strip())
        if m and i + 1 < len(lines) and lines[i + 1].startswith("% ") and "----" not in lines[i + 1]:
            name = lines[i + 1][2:].strip()
            current = {"name": name, "entries": []}
            groups.append(current)
            pending_comment = []
            i += 3
            continue
        if line.startswith("% ") and current is not None:
            pending_comment.append(line[2:].strip())
        if line.startswith("@"):
            m = re.match(r"@(\w+)\{([^,]+),", line)
            etype, key = m.group(1), m.group(2)
            raw = [line]
            body = []
            i += 1
            while i < len(lines) and not lines[i].startswith("}"):
                body.append(lines[i])
                raw.append(lines[i])
                i += 1
            raw.append("}")
            fields = {}
            for fm in re.finditer(r"(\w+)\s*=\s*\{(.*)\}\s*,?\s*$", "\n".join(body), re.M):
                fields[fm.group(1).lower()] = fm.group(2)
            comment = " ".join(pending_comment)
            verified = "direct" if "[direct]" in comment else "scholar"
            entry = {"type": etype, "key": key, "fields": fields, "verified": verified,
                     "raw": "\n".join(raw)}
            if current is None:
                current = {"name": "Other", "entries": []}
                groups.append(current)
            current["entries"].append(entry)
            pending_comment = []
        i += 1
    return groups


def fmt_authors(raw: str) -> str:
    parts = [p.strip() for p in delatex(raw).split(" and ")]
    out = []
    for p in parts:
        if "," in p:
            last, first = [x.strip() for x in p.split(",", 1)]
            name = f"{first} {last}"
        else:
            name = p
        if name in PIS:
            out.append(f"<strong>{html.escape(name)}</strong>")
        else:
            out.append(html.escape(name))
    return ", ".join(out)


def venue_of(e) -> str:
    f = e["fields"]
    bits = []
    if "journal" in f:
        v = delatex(f["journal"])
        if f.get("volume"):
            v += f" {f['volume']}"
            if f.get("number"):
                v += f"({f['number']})"
        if f.get("pages"):
            v += ":" + delatex(f["pages"]).replace("–", "–")
        bits.append(v)
    elif "booktitle" in f:
        bits.append(delatex(f["booktitle"]))
        if f.get("pages"):
            bits.append("pp. " + delatex(f["pages"]))
    elif "eprint" in f:
        bits.append(f"arXiv:{f['eprint']}")
    elif "howpublished" in f:
        bits.append(delatex(f["howpublished"]))
    return ", ".join(bits)


def arxiv_id(e):
    f = e["fields"]
    if f.get("eprint"):
        return f["eprint"]
    m = re.search(r"arXiv:([\d.]+)", f.get("note", ""))
    return m.group(1) if m else None


def pdf_url(e, proof) -> str:
    if proof.get("pdf"):
        return proof["pdf"]
    aid = arxiv_id(e)
    if aid:
        return f"https://arxiv.org/pdf/{aid}"
    u = e["fields"].get("url", "")
    if "aclanthology" in u:
        return u.rstrip("/") + ".pdf"
    m = re.search(r"openreview\.net/forum\?id=(\S+)", u)
    if m:
        return f"https://openreview.net/pdf?id={m.group(1)}"
    return ""


def links_of(e, proof) -> str:
    f = e["fields"]
    out = []
    if f.get("doi"):
        out.append(f'<a href="https://doi.org/{f["doi"]}">DOI</a>')
    aid = arxiv_id(e)
    if aid:
        out.append(f'<a href="https://arxiv.org/abs/{aid}">arXiv</a>')
    if f.get("url"):
        out.append(f'<a href="{f["url"]}">link</a>')
    pu = pdf_url(e, proof)
    if pu:
        out.append(f'<a href="{pu}">PDF</a>')
    return " · ".join(out)


def main():
    groups = parse_bib(BIB.read_text())
    proofs = json.loads(PROOFS.read_text()) if PROOFS.exists() else {}
    total = sum(len(g["entries"]) for g in groups)
    today = date.today().isoformat()

    cards = []
    filter_buttons = ['<button class="fbtn active" data-group="all">All (%d)</button>' % total]
    for gi, g in enumerate(groups):
        gname = html.escape(g["name"])
        filter_buttons.append(
            f'<button class="fbtn" data-group="g{gi}">{gname} ({len(g["entries"])})</button>'
        )
        cards.append(f'<h2 class="ghead" data-group="g{gi}">{gname}</h2>')
        entries = sorted(g["entries"], key=lambda e: -int(e["fields"].get("year", "0")))
        for e in entries:
            f = e["fields"]
            proof = proofs.get(e["key"], {})
            title = delatex(f.get("title", e["key"]))
            year = f.get("year", "")
            vtag = ("verified in paper text" if e["verified"] == "direct"
                    else "verified via Scholar full-text index")
            vclass = e["verified"]
            if proof.get("quote"):
                src = proof.get("source") or ""
                srclink = (f'<a href="{src}">source</a>' if src.startswith("http") else html.escape(src))
                proofbox = f"""
        <blockquote>“{html.escape(proof['quote'])}”</blockquote>
        <div class="proofsrc">Quoted from the paper's full text ({srclink}).</div>"""
            else:
                proofbox = f"""
        <div class="proofsrc">The paper's full text matches the DFG Project-ID
        <code>528483508</code> in <a href="{SCHOLAR_URL}">Google Scholar's full-text index</a>;
        the full text itself is not freely accessible for direct quotation.</div>"""
            cards.append(f"""
<article class="pub" data-group="g{gi}">
  <div class="pubrow">
    <span class="year">{year}</span>
    <div class="pubmain">
      <div class="ptitle">{html.escape(title)}</div>
      <div class="pauthors">{fmt_authors(f.get('author', ''))}</div>
      <div class="pvenue">{html.escape(venue_of(e))}</div>
      <div class="pmeta">{links_of(e, proof)}<button class="bibbtn togglebtn" data-target="bib-{e['key']}">BibTeX</button><button class="bibbtn togglebtn" data-target="proof-{e['key']}">Proof</button><span class="vtag {vclass}" title="{vtag}">{'✓ ' + vtag}</span></div>
      <div class="bibbox" id="bib-{e['key']}" hidden>
        <button class="copybtn" data-key="{e['key']}">Copy</button>
        <pre>{html.escape(e['raw'])}</pre>
      </div>
      <div class="proofbox" id="proof-{e['key']}" hidden>{proofbox}
      </div>
    </div>
  </div>
</article>""")

    html_out = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ApplFM Publications</title>
<style>
:root {{
  --bg: #faf9f7; --card: #ffffff; --ink: #1a1c20; --muted: #5b6169;
  --accent: #0e6e5c; --accent-soft: #e3f0ec; --line: #e4e1dc; --chip: #f0eee9;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #14161a; --card: #1c1f24; --ink: #e8e6e1; --muted: #9aa1ab;
    --accent: #4cc2a9; --accent-soft: #17332d; --line: #2a2e35; --chip: #23272e;
  }}
}}
* {{ box-sizing: border-box; margin: 0; }}
body {{
  background: var(--bg); color: var(--ink);
  font: 16px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  padding: 0 1rem 4rem;
}}
.wrap {{ max-width: 860px; margin: 0 auto; }}
header {{ padding: 3rem 0 1.5rem; }}
h1 {{ font-size: 2rem; letter-spacing: -0.02em; }}
.sub {{ color: var(--muted); margin-top: 0.5rem; max-width: 46rem; }}
.sub a {{ color: var(--accent); }}
.stats {{ margin-top: 1rem; color: var(--muted); font-size: 0.9rem; }}
.filters {{ display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 1.2rem 0 2rem; }}
.fbtn {{
  border: 1px solid var(--line); background: var(--card); color: var(--ink);
  border-radius: 999px; padding: 0.3rem 0.8rem; font-size: 0.82rem; cursor: pointer;
}}
.fbtn.active {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
.ghead {{ font-size: 1.05rem; margin: 2rem 0 0.8rem; color: var(--accent); }}
.pub {{
  background: var(--card); border: 1px solid var(--line); border-radius: 10px;
  padding: 0.9rem 1rem; margin-bottom: 0.6rem;
}}
.pubrow {{ display: flex; gap: 0.9rem; }}
.year {{
  flex: 0 0 auto; align-self: flex-start; font-size: 0.78rem; font-weight: 600;
  background: var(--chip); border-radius: 6px; padding: 0.15rem 0.45rem; color: var(--muted);
}}
.ptitle {{ font-weight: 600; }}
.pauthors {{ font-size: 0.88rem; color: var(--muted); margin-top: 0.15rem; }}
.pauthors strong {{ color: var(--ink); font-weight: 600; }}
.pvenue {{ font-size: 0.88rem; margin-top: 0.15rem; font-style: italic; }}
.pmeta {{ font-size: 0.82rem; margin-top: 0.3rem; display: flex; gap: 0.8rem; flex-wrap: wrap; align-items: center; }}
.pmeta a {{ color: var(--accent); text-decoration: none; }}
.pmeta a:hover {{ text-decoration: underline; }}
.vtag {{ color: var(--muted); }}
.vtag.direct {{ color: var(--accent); }}
.bibbtn {{
  border: 1px solid var(--line); background: var(--chip); color: var(--ink);
  border-radius: 6px; padding: 0.1rem 0.5rem; font-size: 0.78rem; cursor: pointer;
}}
.bibbtn:hover, .bibbtn.open {{ border-color: var(--accent); color: var(--accent); }}
.bibbox {{ position: relative; margin-top: 0.6rem; }}
.bibbox pre {{
  background: var(--chip); border: 1px solid var(--line); border-radius: 8px;
  padding: 0.7rem 0.9rem; font-size: 0.76rem; line-height: 1.45;
  overflow-x: auto; white-space: pre;
}}
.copybtn {{
  position: absolute; top: 0.45rem; right: 0.45rem;
  border: 1px solid var(--line); background: var(--card); color: var(--muted);
  border-radius: 6px; padding: 0.1rem 0.5rem; font-size: 0.72rem; cursor: pointer;
}}
.copybtn:hover {{ color: var(--accent); border-color: var(--accent); }}
.proofbox {{
  margin-top: 0.6rem; background: var(--accent-soft); border: 1px solid var(--line);
  border-left: 3px solid var(--accent); border-radius: 8px; padding: 0.7rem 0.9rem;
}}
.proofbox blockquote {{ font-size: 0.88rem; font-style: italic; }}
.proofsrc {{ font-size: 0.78rem; color: var(--muted); margin-top: 0.35rem; }}
.proofsrc a {{ color: var(--accent); }}
footer {{ margin-top: 3rem; color: var(--muted); font-size: 0.85rem; }}
footer a {{ color: var(--accent); }}
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>ApplFM Publications</h1>
  <p class="sub">Publications acknowledging the DFG project
  <a href="https://projekt.bht-berlin.de/impact/forschung/berlin-initiative-for-applied-foundation-model-research-appl-fm">ApplFM
  — Berlin Initiative for Applied Foundation Model Research</a>
  (DFG Research Impulses FIP&nbsp;12, Project-ID&nbsp;528483508). Only papers whose full text
  mentions the project are listed. Names of participating PIs are shown in bold.</p>
  <p class="stats">{total} publications · last checked {today} ·
  <a href="https://github.com/erodner/applfm-pubs">BibTeX on GitHub</a></p>
</header>
<div class="filters">{''.join(filter_buttons)}</div>
{''.join(cards)}
<footer>Generated from <a href="https://github.com/erodner/applfm-pubs/blob/main/applfm.bib">applfm.bib</a>
by <code>generate_site.py</code>.</footer>
</div>
<script>
document.querySelectorAll('.togglebtn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    const box = document.getElementById(btn.dataset.target);
    box.hidden = !box.hidden;
    btn.classList.toggle('open', !box.hidden);
  }});
}});
document.querySelectorAll('.copybtn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    const pre = btn.parentElement.querySelector('pre');
    navigator.clipboard.writeText(pre.textContent).then(() => {{
      btn.textContent = 'Copied!';
      setTimeout(() => {{ btn.textContent = 'Copy'; }}, 1500);
    }});
  }});
}});
document.querySelectorAll('.fbtn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.fbtn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const g = btn.dataset.group;
    document.querySelectorAll('.pub, .ghead').forEach(el => {{
      el.style.display = (g === 'all' || el.dataset.group === g) ? '' : 'none';
    }});
  }});
}});
</script>
</body>
</html>
"""
    OUT.write_text(html_out)
    print(f"Wrote {OUT} ({total} publications, {len(groups)} groups)")


if __name__ == "__main__":
    main()
