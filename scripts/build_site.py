#!/usr/bin/env python3
"""Generate a static site from generated/registry.json.

Produces one page per documented breaking change, titled with the deprecated
symbol, so that a developer searching the error they just hit lands on the
migration. Also publishes the registry JSON at a stable versioned path.

Usage:
    python scripts/build_site.py [--out site]
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "generated" / "registry.json"

REPO_URL = "https://github.com/onthedrops/ai-sdk-breakage-registry"

CSS = """
*{box-sizing:border-box}
body{margin:0;padding:2rem 1rem;font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#1a1a1a;background:#fff}
main{max-width:52rem;margin:0 auto}
a{color:#0b5fff}
h1{font-size:1.6rem;line-height:1.3;margin:0 0 .5rem}
h2{font-size:1.15rem;margin:2rem 0 .5rem}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.9em;background:#f4f4f5;padding:.1em .35em;border-radius:3px}
pre{background:#f7f7f8;border:1px solid #e5e5e7;border-radius:6px;padding:.85rem 1rem;overflow-x:auto}
pre code{background:none;padding:0}
.meta{color:#666;font-size:.9rem;margin-bottom:1.5rem}
.badge{display:inline-block;font-size:.75rem;padding:.15em .5em;border-radius:3px;background:#eef;color:#334;margin-right:.4rem}
.sev-critical{background:#fde8e8;color:#911}
.sev-high{background:#fff0e0;color:#8a4b00}
.sev-medium{background:#fffbe6;color:#7a5c00}
.sev-low{background:#eef7ee;color:#2a5a2a}
table{border-collapse:collapse;width:100%;font-size:.92rem}
th,td{text-align:left;padding:.45rem .6rem;border-bottom:1px solid #eee}
th{font-weight:600;color:#444}
nav{font-size:.9rem;margin-bottom:1.5rem}
footer{margin-top:3rem;padding-top:1rem;border-top:1px solid #eee;color:#666;font-size:.85rem}
input[type=search]{width:100%;padding:.7rem .9rem;font-size:1rem;border:1px solid #ccc;border-radius:6px;margin:1rem 0}
.hit{padding:.6rem 0;border-bottom:1px solid #f0f0f0}
.hit small{color:#666}
.arrow{color:#999;padding:0 .4em}
"""


def esc(s) -> str:
    return html.escape(str(s or ""))


def slug(*parts: str) -> str:
    s = "-".join(str(p) for p in parts).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-{2,}", "-", s).strip("-")[:120]


def page(title: str, body: str, description: str = "", depth: int = 0) -> str:
    up = "../" * depth
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<style>{CSS}</style>
</head>
<body>
<main>
<nav><a href="{up}index.html">AI SDK Breakage Registry</a></nav>
{body}
<footer>
Part of the <a href="{REPO_URL}">AI SDK Breakage Registry</a> &mdash;
every entry cited to official vendor documentation and re-verified against the live source.
</footer>
</main>
</body>
</html>
"""


def change_page(entry: dict, change: dict, depth: int) -> tuple[str, str]:
    pkg = entry.get("package", "")
    before = change.get("symbol_before", "")
    after = change.get("symbol_after", "")
    to_v = entry.get("to_version_range", "")
    sev = entry.get("severity", "")

    title = f"{before} — removed in {pkg} {to_v}"
    if after:
        title = f"{before} → {after} ({pkg} {to_v})"

    desc = (change.get("migration_note") or "")[:180]

    parts = [f"<h1><code>{esc(before)}</code></h1>"]
    parts.append(
        f'<p class="meta">'
        f'<span class="badge sev-{esc(sev)}">{esc(sev)}</span>'
        f'<code>{esc(pkg)}</code> ({esc(entry.get("ecosystem",""))}) '
        f'{esc(entry.get("from_version_range",""))} <span class="arrow">→</span> {esc(to_v)}'
        f' &middot; {esc(change.get("change_type",""))}</p>'
    )
    if after:
        parts.append(f"<h2>Replacement</h2><p><code>{esc(after)}</code></p>")
    if change.get("migration_note"):
        parts.append(f"<h2>What changed</h2><p>{esc(change['migration_note'])}</p>")
    if change.get("before"):
        parts.append(f"<h2>Before</h2><pre><code>{esc(change['before'].rstrip())}</code></pre>")
    if change.get("after"):
        parts.append(f"<h2>After</h2><pre><code>{esc(change['after'].rstrip())}</code></pre>")

    srcs = entry.get("sources") or []
    if srcs:
        items = "".join(
            f'<li><a href="{esc(s.get("url"))}" rel="nofollow">{esc(s.get("title") or s.get("url"))}</a></li>'
            for s in srcs
        )
        parts.append(f"<h2>Sources</h2><ul>{items}</ul>")
    parts.append(
        f'<p class="meta">Last verified {esc(entry.get("last_verified",""))} '
        f'&middot; confidence {esc(entry.get("confidence",""))}</p>'
    )
    up = "../" * depth
    pkg_href = f'{up}p/{slug(entry.get("ecosystem",""), pkg, entry.get("to_version_range",""))}.html'
    parts.append(f'<p><a href="{pkg_href}">All {esc(pkg)} breaking changes</a></p>')

    return title, page(title, "\n".join(parts), desc, depth)


def build(out: Path) -> None:
    registry = json.loads(REGISTRY.read_text())
    entries = registry.get("entries", [])

    if out.exists():
        shutil.rmtree(out)
    (out / "p").mkdir(parents=True)
    (out / "s").mkdir(parents=True)
    (out / "v1").mkdir(parents=True)

    # Stable, versioned copies of the data.
    payload = REGISTRY.read_text()
    (out / "registry.json").write_text(payload)
    (out / "v1" / "registry.json").write_text(payload)

    index_rows = []
    search_index = []
    n_changes = 0

    for entry in entries:
        pkg = entry.get("package", "")
        eco = entry.get("ecosystem", "")
        pkg_slug = slug(eco, pkg, entry.get("to_version_range", ""))
        change_links = []

        for change in entry.get("changes", []):
            n_changes += 1
            before = change.get("symbol_before", "")
            c_slug = slug(pkg, before) or slug(pkg, str(n_changes))
            path = out / "s" / f"{c_slug}.html"
            i = 2
            while path.exists():
                path = out / "s" / f"{c_slug}-{i}.html"
                i += 1
            title, doc = change_page(entry, change, depth=1)
            path.write_text(doc)
            rel = f"s/{path.name}"
            change_links.append(
                f'<tr><td><a href="../{rel}"><code>{esc(before)}</code></a></td>'
                f"<td><code>{esc(change.get('symbol_after',''))}</code></td>"
                f"<td>{esc(change.get('change_type',''))}</td></tr>"
            )
            search_index.append(
                {
                    "s": before,
                    "a": change.get("symbol_after", ""),
                    "p": pkg,
                    "u": rel,
                }
            )

        body = [
            f"<h1>{esc(pkg)} breaking changes</h1>",
            f'<p class="meta"><span class="badge sev-{esc(entry.get("severity",""))}">'
            f'{esc(entry.get("severity",""))}</span>'
            f'{esc(eco)} &middot; {esc(entry.get("from_version_range",""))} '
            f'<span class="arrow">→</span> {esc(entry.get("to_version_range",""))} '
            f'&middot; {len(entry.get("changes", []))} documented changes</p>',
            f"<p>{esc(entry.get('summary',''))}</p>",
            "<table><thead><tr><th>Deprecated</th><th>Replacement</th><th>Type</th></tr></thead>"
            f"<tbody>{''.join(change_links)}</tbody></table>",
        ]
        (out / "p" / f"{pkg_slug}.html").write_text(
            page(f"{pkg} breaking changes ({entry.get('to_version_range','')})",
                 "\n".join(body), entry.get("summary", "")[:180], depth=1)
        )

        index_rows.append(
            f'<tr><td><a href="p/{pkg_slug}.html"><code>{esc(pkg)}</code></a></td>'
            f"<td>{esc(eco)}</td>"
            f"<td>{esc(entry.get('from_version_range',''))} → {esc(entry.get('to_version_range',''))}</td>"
            f"<td>{len(entry.get('changes', []))}</td></tr>"
        )

    index_body = f"""
<h1>AI SDK Breakage Registry</h1>
<p>{n_changes} documented breaking changes across {len(entries)} AI SDK version transitions.
Every change is cited to official vendor documentation and re-verified against the live source.</p>

<input type="search" id="q" placeholder="Paste the symbol or error you hit, e.g. openai.ChatCompletion.create" autocomplete="off">
<div id="results"></div>

<h2>Coverage</h2>
<table><thead><tr><th>Package</th><th>Ecosystem</th><th>Transition</th><th>Changes</th></tr></thead>
<tbody>{''.join(index_rows)}</tbody></table>

<h2>Use the data</h2>
<p>The registry is published as JSON at a stable path:</p>
<pre><code>curl -s https://onthedrops.github.io/ai-sdk-breakage-registry/v1/registry.json</code></pre>
<p>An <a href="{REPO_URL}/tree/main/mcp">MCP server</a> exposes the same data to coding agents,
so an assistant can check a call before it writes it.</p>

<script id="idx" type="application/json">{json.dumps(search_index, separators=(",", ":"))}</script>
<script>
(function(){{
  var idx = JSON.parse(document.getElementById('idx').textContent);
  var q = document.getElementById('q'), out = document.getElementById('results');
  q.addEventListener('input', function(){{
    var v = q.value.trim().toLowerCase();
    if (v.length < 2) {{ out.innerHTML = ''; return; }}
    var hits = idx.filter(function(r){{
      return (r.s && r.s.toLowerCase().indexOf(v) !== -1) || (v.indexOf(r.s.toLowerCase()) !== -1 && r.s.length > 3);
    }}).slice(0, 25);
    out.innerHTML = hits.length
      ? hits.map(function(r){{
          return '<div class="hit"><a href="' + r.u + '"><code>' + r.s + '</code></a>'
               + (r.a ? ' <span class="arrow">&rarr;</span> <code>' + r.a + '</code>' : '')
               + '<br><small>' + r.p + '</small></div>';
        }}).join('')
      : '<p><small>No documented breakage for that symbol. The registry covers '
        + idx.length + ' changes; absence is not proof the symbol is current.</small></p>';
  }});
}})();
</script>
"""
    (out / "index.html").write_text(
        page("AI SDK Breakage Registry",
             index_body,
             f"{n_changes} documented breaking changes across {len(entries)} AI SDK version transitions, "
             "each cited to official documentation.",
             depth=0)
    )
    (out / ".nojekyll").write_text("")
    print(f"built {out}: {n_changes} change pages, {len(entries)} package pages")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site")
    args = ap.parse_args()
    build(ROOT / args.out)


if __name__ == "__main__":
    main()
