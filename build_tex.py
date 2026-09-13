#!/usr/bin/env python3
"""Render PAPER.md into IEEEtran LaTeX (main.tex) for submission.

Same rule as build_ieee.py: PAPER.md is the single source of truth and main.tex is
GENERATED. Hand-editing the generated artifact is exactly how the HTML preview drifted
out of sync with the paper and kept reporting withdrawn numbers for several revisions.

    python3 build_tex.py

NOT COMPILED OR VERIFIED. There is no LaTeX toolchain on this machine (no pdflatex,
xelatex, latexmk or tectonic), so this output has never been run through a compiler.
Upload main.tex plus figs/loom.png to Overleaf, select pdfLaTeX, and expect to fix
something. Do not submit without compiling it yourself first.

References are emitted as a literal `thebibliography` rather than a .bib file. Every
entry was verified against its primary source by hand; re-parsing that text into BibTeX
fields would risk corrupting citations that are known-correct, for no gain — IEEEtran
accepts thebibliography directly and Overleaf needs no bibtex pass for it.
"""
import re
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "PAPER.md"
OUT = ROOT / "main.tex"
FIG = ROOT / "figs" / "loom.png"

# Non-ASCII actually present in PAPER.md (see the inventory in the commit that added
# this file). Anything not listed here would pass through raw and break pdfLaTeX.
UNI = {
    "\u2014": "---", "\u2013": "--", "\u2212": "$-$", "\u00d7": "$\\times$",
    "\u00a7": "\\S{}", "\u2192": "$\\rightarrow$", "\u00b5": "\\textmu{}",
    "\u2016": "$\\|$", "\u2265": "$\\geq$", "\u2264": "$\\leq$",
    "\u0394": "$\\Delta$", "\u03b5": "$\\varepsilon$", "\u2074": "$^{4}$",
    "\u201c": "``", "\u201d": "''",
    "\u2018": "`", "\u2019": "'", "\u2026": "\\ldots{}", "\u00b7": "$\\cdot$",
}

SPECIALS = [("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("$", r"\$"),
            ("#", r"\#"), ("_", r"\_"), ("{", r"\{"), ("}", r"\}"),
            ("~", r"\textasciitilde{}"), ("^", r"\textasciicircum{}")]

PREAMBLE = r"""\documentclass[conference]{IEEEtran}
\IEEEoverridecommandlockouts
\usepackage{cite}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{textcomp}
\usepackage{xcolor}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{url}
\def\BibTeX{{\rm B\kern-.05em{\sc i\kern-.025em b}\kern-.08em
    T\kern-.1667em\lower.7ex\hbox{E}\kern-.125emX}}
\begin{document}
"""

FIGURE = r"""
\begin{figure*}[t]
\centering
\includegraphics[width=\textwidth]{figs/loom.png}
\caption{The accountability loom. Vertical warp columns are per-deployment stacks;
horizontal weft threads are interaction evidence, drawn with thread weight proportional
to evidentiary class; the central funnel is the shuttle turning flagged threads into
verdicts; the witness-cosigned root is the selvage. The right-hand rail marks the three
policy tiers at their native altitude.}
\label{fig:loom}
\end{figure*}
"""


def esc(s: str) -> str:
    """Escape LaTeX specials. Markdown markers (* [ ]) are not specials, so they
    survive this and are converted afterwards."""
    for a, b in SPECIALS:
        s = s.replace(a, b)
    for a, b in UNI.items():
        s = s.replace(a, b)
    return s


def cites(s: str) -> str:
    """[3]--[5] and [7], [9] -> \\cite{...}. Runs AFTER escaping; brackets are safe."""
    s = re.sub(r"\[(\d+)\]--\[(\d+)\]",
               lambda m: "\\cite{" + ",".join(f"r{i}" for i in
                                              range(int(m[1]), int(m[2]) + 1)) + "}", s)
    # collapse runs of adjacent single cites into one \cite
    s = re.sub(r"\[(\d+)\](?:,\s*\[(\d+)\])*",
               lambda m: "\\cite{" + ",".join("r" + n for n in
                                              re.findall(r"\d+", m.group(0))) + "}", s)
    return s


def inline(s: str, code: list) -> str:
    """Markdown inline -> LaTeX. Code spans are pulled out before escaping so that
    underscores and hashes inside them are not mangled twice. Bare URLs are pulled
    out the same way and come back wrapped in \\url{}, so they hyphenate at
    slashes instead of overrunning the column (r15 was 39pt into the margin)."""
    urls = []
    def _grab_url(m):
        u = m.group(0).rstrip(".,;:")
        urls.append(u)
        return f"\x01{len(urls)-1}\x01" + m.group(0)[len(u):]
    s = re.sub(r"https?://[^\s)\]]+", _grab_url, s)
    s = re.sub(r"`([^`]+)`", lambda m: (code.append(m[1]), f"\x00{len(code)-1}\x00")[1], s)
    s = esc(s)
    # the one figure is referenced from C1; markdown says "(Fig. 1)", LaTeX gets the ref
    s = s.replace("(Fig. 1)", "(Fig.~\\ref{fig:loom})")
    # relational operators need math mode for correct spacing; done here and not in
    # esc() so that < and > inside \texttt code spans are left alone.
    s = s.replace("<", "$<$").replace(">", "$>$")
    # straight ASCII quotes render as two CLOSING quotes in LaTeX; paper titles in the
    # bibliography are full of them, so pair them up properly.
    s = re.sub(r'"([^"]*)"', r"``\1''", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\\textbf{\1}", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\\textit{\1}", s)
    s = cites(s)
    s = re.sub(r"\x00(\d+)\x00",
               lambda m: "\\texttt{" + esc(code[int(m[1])]) + "}", s)
    return re.sub(r"\x01(\d+)\x01", lambda m: "\\url{" + urls[int(m[1])] + "}", s)


def render(md: str) -> str:
    lines, out, i, code = md.split("\n"), [], 0, []
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("## "):                                    # section
            t = re.sub(r"^[IVX]+\.\s*", "", ln[3:].strip())
            out.append("\n\\section{%s}" % inline(t, code)); i += 1
            if t == "Introduction":
                out.append(FIGURE)
            continue
        if ln.startswith("### "):                                   # subsection
            t = re.sub(r"^[A-Z]\.\s*", "", ln[4:].strip())
            out.append("\n\\subsection{%s}" % inline(t, code)); i += 1; continue
        if re.match(r"^\s*[-*] ", ln):                              # bullets
            buf = []
            while i < len(lines) and re.match(r"^\s*[-*] ", lines[i]):
                buf.append("\\item " + inline(re.sub(r"^\s*[-*] ", "", lines[i]), code))
                i += 1
            out.append("\\begin{itemize}\n" + "\n".join(buf) + "\n\\end{itemize}")
            continue
        if ln.startswith("|"):                                      # table
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(lines[i]); i += 1
            cells = [[c.strip() for c in r.strip("|").split("|")] for r in rows]
            cells = [c for c in cells if not all(set(x) <= set("-: ") for x in c)]
            n = max(len(r) for r in cells)
            t = ["\n\\begin{table}[t]\n\\centering\n\\caption{}\n"
                 "\\begin{tabular}{@{}" + "l" * n + "@{}}\n\\hline"]
            for r, row in enumerate(cells):
                row = row + [""] * (n - len(row))
                t.append(" & ".join(inline(c, code) for c in row) + " \\\\")
                if r == 0:
                    t.append("\\hline")
            t.append("\\hline\n\\end{tabular}\n\\end{table}")
            out.append("\n".join(t)); continue
        if ln.strip():                                              # paragraph
            buf = [ln]; i += 1
            while i < len(lines) and lines[i].strip() and not re.match(
                    r"^(#{2,3} |\||```|\s*[-*] |\d+\. )", lines[i]):
                buf.append(lines[i]); i += 1
            out.append("\n" + inline(" ".join(x.strip() for x in buf), code)); continue
        i += 1
    return "\n".join(out)


def main():
    md = SRC.read_text()
    code = []
    title = re.search(r"^# (.+)$", md, re.M)[1]
    abstract = re.search(r"^## Abstract\s*\n+(.+?)\n\n", md, re.S | re.M)[1]
    kw = re.search(r"\*\*Index terms\*\* --- (.+?)\.", md.replace("\u2014", "---"), re.S)
    kw = kw[1].replace("\n", " ") if kw else ""

    body_md = md[md.index("## I. Introduction"):]
    at = body_md.index("## References")
    body, refs_md = body_md[:at], body_md[at:]
    refs = re.findall(r"^(\d+)\.\s+(.*)$", refs_md, re.M)

    if not FIG.exists():
        print(f"WARNING: {FIG} missing — \\includegraphics will fail")

    bib = ["\n\\begin{thebibliography}{%d}" % len(refs)]
    for n, text in refs:
        bib.append("\\bibitem{r%s} %s" % (n, inline(text, code)))
    bib.append("\\end{thebibliography}")

    doc = (PREAMBLE
           + "\n\\title{%s}\n" % inline(title, code)
           + "\n\\author{\\IEEEauthorblockN{Saish Sanjay Shinde}\n"
             "\\IEEEauthorblockA{\\textit{San Jos\\'e State University} \\\\\n"
             "San Jos\\'e, CA, USA \\\\\nsaish.shinde@sjsu.edu}}\n"
           + "\n\\maketitle\n"
           + "\n\\begin{abstract}\n%s\n\\end{abstract}\n" % inline(abstract, code)
           + "\n\\begin{IEEEkeywords}\n%s\n\\end{IEEEkeywords}\n" % inline(kw, code)
           + render(body) + "\n" + "\n".join(bib) + "\n\n\\end{document}\n")

    OUT.write_text(doc)
    SAFE = set("\u00e4\u00e9\u00fc\u00f6\u00e1\u00e8\u00ed\u00f3\u00fa\u00f1\u00e7\u00c9\u00c4")  # inputenc handles these directly
    leftover = sorted({c for c in doc if ord(c) > 126 and c not in SAFE})
    print(f"wrote {OUT}  ({len(refs)} refs, {len(doc.split())} tokens)")
    print("unmapped non-ASCII:", leftover if leftover else "none")
    print("NOT COMPILED — no LaTeX toolchain here. Build on Overleaf before submitting.")


if __name__ == "__main__":
    main()
