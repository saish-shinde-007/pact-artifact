#!/usr/bin/env python3
"""Render PAPER.md into IEEEtran main.tex - main.tex is GENERATED, never hand-edited.
References emit as an inline thebibliography, bare URLs get url-wrapped, '(Fig. 1)'
maps to the loom figure ref. Overleaf: main.tex + figs/loom.png, pdfLaTeX.
"""
import re
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "PAPER.md"
import sys

# --anon: SaTML-style double-blind build (main-anon.tex; author block swapped,
# nothing else differs). Default build is the named arXiv/camera-ready one.
ANON = "--anon" in sys.argv
ARTIFACT = ("the anonymized repository accompanying this submission "
            "(https://anonymous.4open.science/r/pact-review-2027)" if ANON else
            "https://github.com/saish-shinde-007/pact-paper, archived with DOI "
            "10.5281/zenodo.22738800")
OUT = ROOT / ("main-anon.tex" if ANON else "main.tex")
AUTHOR_BLOCK = (
    "\n\\author{\\IEEEauthorblockN{Anonymous Author(s)}\n"
    "\\IEEEauthorblockA{Double-blind submission to IEEE SaTML 2027}}\n"
    if ANON else
    "\n\\author{\\IEEEauthorblockN{Saish Sanjay Shinde}\n"
    "\\IEEEauthorblockA{\\textit{San Jos\\'e State University} \\\\\n"
    "San Jos\\'e, CA, USA \\\\\nsaish.shinde@sjsu.edu}}\n")
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
    r"""Markdown inline -> LaTeX. Code spans and bare URLs are pulled out before
    escaping (so nothing is mangled twice) and come back as texttt / url-wrapped,
    which lets long URLs break at slashes instead of overrunning the column."""
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
            # SaTML-required statements are unnumbered and sit before the references
            star = "*" if t in ("Open Science", "LLM Usage Considerations",
                                "Ethical Considerations") else ""
            out.append("\n\\section%s{%s}" % (star, inline(t, code))); i += 1
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
           + AUTHOR_BLOCK
           + "\n\\maketitle\n"
           + "\n\\begin{abstract}\n%s\n\\end{abstract}\n" % inline(abstract, code)
           + "\n\\begin{IEEEkeywords}\n%s\n\\end{IEEEkeywords}\n" % inline(kw, code)
           + render(body) + "\n" + "\n".join(bib) + "\n\n\\end{document}\n")

    OUT.write_text(doc.replace("ARTIFACT-LINK", ARTIFACT))
    SAFE = set("\u00e4\u00e9\u00fc\u00f6\u00e1\u00e8\u00ed\u00f3\u00fa\u00f1\u00e7\u00c9\u00c4")  # inputenc handles these directly
    leftover = sorted({c for c in doc if ord(c) > 126 and c not in SAFE})
    print(f"wrote {OUT}  ({len(refs)} refs, {len(doc.split())} tokens)")
    print("unmapped non-ASCII:", leftover if leftover else "none")
    print("NOT COMPILED — no LaTeX toolchain here. Build on Overleaf before submitting.")


if __name__ == "__main__":
    main()
