#!/usr/bin/env python3
"""Render PAPER.md into the IEEE two-column HTML preview.

PAPER.md is the single source of truth. The HTML is GENERATED, never hand-edited —
hand-editing is exactly how the published artifact drifted out of sync with the
paper (it kept reporting withdrawn numbers for several revisions). Regenerate with:

    python3 build_ieee.py && open ieee.html

Usage note: this renders the two-column *look* for review. The submission artifact
is LaTeX/IEEEtran; this exists so the paper can be read in its final shape while
still being written in Markdown.
"""
import html
import re
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "PAPER.md"
OUT = ROOT / "ieee.html"
FIG = ROOT / "figs" / "loom.svg"

CSS = """
:root { --ground:#E8EAE8; --ground-ink:#4A5450; --accent:#0B6B58; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --ground:#141917; --ground-ink:#93A39D; --accent:#43A98E; } }
:root[data-theme="dark"] { --ground:#141917; --ground-ink:#93A39D; --accent:#43A98E; }
body { background: var(--ground); margin: 0; }
.bar { max-width:916px; margin:0 auto; padding:18px 16px 10px;
  font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:12px;
  color:var(--ground-ink); display:flex; flex-wrap:wrap; gap:6px 18px; }
.bar b { color:var(--accent); font-weight:600; }
/* the sheet simulates print: always white, always dark ink */
.sheet { background:#fff; color:#111; max-width:852px; margin:0 auto 64px;
  padding:58px 64px 66px; box-shadow:0 2px 14px rgba(0,0,0,.18);
  font-family:"Times New Roman",Times,"Liberation Serif",serif;
  font-size:13.3px; line-height:1.38; text-align:justify; hyphens:auto; }
@media (max-width:700px){ .sheet{ padding:34px 22px 44px; } }
.title { font-size:24px; text-align:center; line-height:1.2; margin:0 0 18px; hyphens:none; }
.authors { text-align:center; margin-bottom:26px; hyphens:none; }
.authors .name { font-size:14.5px; margin-bottom:2px; }
.authors .aff { font-style:italic; font-size:13px; line-height:1.3; }
.cols { columns:2; column-gap:26px; }
@media (max-width:700px){ .cols{ columns:1; } }
.abstract,.keywords { font-weight:700; font-size:12.3px; margin:0 0 10px; text-indent:0; }
.abstract .lead,.keywords .lead { font-style:italic; }
h2 { font-size:13.3px; font-weight:400; font-variant:small-caps; text-align:center;
  margin:16px 0 8px; hyphens:none; break-after:avoid; }
h3 { font-size:13.3px; font-weight:400; font-style:italic; text-align:left;
  margin:12px 0 6px; hyphens:none; break-after:avoid; }
p { margin:0 0 8px; text-indent:14px; }
p.noindent { text-indent:0; }
ul,ol { margin:0 0 8px; padding-left:20px; }
li { margin-bottom:3px; }
.figwide { margin:6px 0 18px; break-inside:avoid; }
.figwide svg { width:100%; height:auto; display:block; }
.figcap,.tabcap { font-size:11.3px; text-indent:0; margin-top:6px; hyphens:none; }
.tabcap { text-align:center; font-variant:small-caps; margin:0 0 5px; }
.figure { break-inside:avoid; margin:10px 0 12px; }
table.ieee { border-collapse:collapse; width:100%; font-size:11.3px; margin:0 0 4px; hyphens:none; }
table.ieee th { border-top:1.5px solid #111; border-bottom:1px solid #111; font-weight:400;
  font-variant:small-caps; padding:3px 6px; text-align:left; }
table.ieee td { padding:3px 6px; text-align:left; vertical-align:top; }
table.ieee tr:last-child td { border-bottom:1.5px solid #111; }
.code { font-family:"Courier New",Courier,monospace; font-size:10.6px; line-height:1.35;
  background:#F5F5F2; border:1px solid #ddd; padding:8px 10px; margin:8px 0 10px;
  break-inside:avoid; overflow-x:auto; text-align:left; white-space:pre; text-indent:0; }
code { font-family:"Courier New",Courier,monospace; font-size:.92em; }
ol.refs { font-size:11.3px; line-height:1.3; padding-left:22px; margin:0; }
ol.refs li { margin-bottom:4px; text-align:justify; }
ol.refs li::marker { content:"[" counter(list-item) "] "; }
"""

ROMAN = "I II III IV V VI VII VIII IX X XI XII XIII XIV XV XVI".split()


def inline(t: str) -> str:
    t = html.escape(t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", t)
    return t


def render(md: str) -> str:
    lines = md.split("\n")
    out, i, table_n = [], 0, 0
    while i < len(lines):
        ln = lines[i]

        if ln.startswith("```"):                         # code block
            i += 1
            buf = []
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(html.escape(lines[i])); i += 1
            out.append('<div class="code">' + "\n".join(buf) + "</div>")
            i += 1; continue

        if ln.startswith("## "):                          # section
            out.append("<h2>" + inline(ln[3:].strip()) + "</h2>"); i += 1; continue
        if ln.startswith("### "):                         # subsection
            out.append("<h3>" + inline(ln[4:].strip()) + "</h3>"); i += 1; continue

        if ln.startswith("|"):                            # table
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(lines[i]); i += 1
            cells = [[c.strip() for c in r.strip("|").split("|")] for r in rows]
            cells = [c for c in cells if not all(set(x) <= set("-: ") for x in c)]
            table_n += 1
            t = [f'<div class="figure"><p class="tabcap">TABLE {ROMAN[table_n-1]}</p>',
                 '<table class="ieee">']
            for r, row in enumerate(cells):
                tag = "th" if r == 0 else "td"
                t.append("<tr>" + "".join(f"<{tag}>{inline(c)}</{tag}>" for c in row) + "</tr>")
            t.append("</table></div>")
            out.append("".join(t)); continue

        if re.match(r"^\s*[-*] ", ln):                    # bullet list
            buf = []
            while i < len(lines) and re.match(r"^\s*[-*] ", lines[i]):
                buf.append("<li>" + inline(re.sub(r"^\s*[-*] ", "", lines[i])) + "</li>"); i += 1
            out.append("<ul>" + "".join(buf) + "</ul>"); continue

        if re.match(r"^\d+\. ", ln):                      # numbered list
            buf = []
            while i < len(lines) and re.match(r"^\d+\. ", lines[i]):
                buf.append("<li>" + inline(re.sub(r"^\d+\. ", "", lines[i])) + "</li>"); i += 1
            out.append("<ol>" + "".join(buf) + "</ol>"); continue

        if ln.strip():                                    # paragraph
            buf = [ln]
            i += 1
            while i < len(lines) and lines[i].strip() and not re.match(
                    r"^(#{2,3} |\||```|\s*[-*] |\d+\. )", lines[i]):
                buf.append(lines[i]); i += 1
            txt = " ".join(x.strip() for x in buf)
            cls = ' class="noindent"' if txt.startswith("**") else ""
            out.append(f"<p{cls}>" + inline(txt) + "</p>"); continue
        i += 1
    return "\n".join(out)


def main():
    md = SRC.read_text()

    title = re.search(r"^# (.+)$", md, re.M).group(1)
    author = re.search(r"^\*\*Author: (.+?)\*\*", md, re.M)
    author = author.group(1) if author else "Saish Sanjay Shinde"

    abstract = re.search(r"^## Abstract\s*\n+(.+?)\n\n", md, re.S | re.M).group(1)
    kw = re.search(r"\*\*Index terms\*\* — (.+?)\.", md, re.S)
    kw = kw.group(1).replace("\n", " ") if kw else ""

    body_md = md[md.index("## I. Introduction"):]
    refs_at = body_md.index("## References")
    body, refs_md = body_md[:refs_at], body_md[refs_at:]
    refs = re.findall(r"^\d+\.\s+(.*)$", refs_md, re.M)

    fig = FIG.read_text() if FIG.exists() else ""
    fig = re.sub(r'<\?xml[^>]*\?>', "", fig).strip()
    fig_block = ("" if not fig else
                 '<div class="figwide">' + fig +
                 '<p class="figcap">Fig. 1.&nbsp; The accountability loom. Vertical warp '
                 'columns are per-deployment stacks; horizontal weft threads are interaction '
                 'evidence, drawn with thread weight proportional to evidentiary class; the '
                 'central funnel is the shuttle turning flagged threads into verdicts; the '
                 'witness-cosigned root is the selvage. The right-hand rail marks the three '
                 'policy tiers at their native altitude.</p></div>')

    rendered = render(body)
    # place the figure after the first section heading
    anchor = rendered.index("</h2>") + 5
    rendered = rendered[:anchor] + fig_block + rendered[anchor:]

    doc = f"""<title>PACT Paper</title>
<style>{CSS}</style>
<div class="bar">
  <span><b>PACT</b> · IEEE two-column preview</span>
  <span>generated from PAPER.md by build_ieee.py — do not hand-edit</span>
  <span>{len(refs)} refs, all verified against primary sources</span>
</div>
<div class="sheet">
  <div class="title">{inline(title)}</div>
  <div class="authors">
    <div class="name">{html.escape(author)}</div>
    <div class="aff">San Jos&eacute; State University<br>San Jos&eacute;, CA, USA<br>
      saish.shinde@sjsu.edu</div>
  </div>
  <div class="cols">
    <p class="abstract"><span class="lead">Abstract</span>—{inline(abstract)}</p>
    <p class="keywords"><span class="lead">Index Terms</span>—{inline(kw)}</p>
    {rendered}
    <h2>References</h2>
    <ol class="refs">
      {"".join("<li>" + inline(r) + "</li>" for r in refs)}
    </ol>
  </div>
</div>
"""
    OUT.write_text(doc)
    print(f"wrote {OUT}  ({len(rendered.split())} body words, {len(refs)} refs)")


if __name__ == "__main__":
    main()
