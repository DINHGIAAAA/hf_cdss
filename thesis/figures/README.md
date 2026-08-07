# Thesis figures

All diagrams are generated with [Archify](https://github.com/tt-a1i/archify) from JSON under `archify/`, delivered to interactive HTML under `html/`.

Chapter manuscripts embed **standalone wrapper pages** under `chapters/` (title, caption, iframe to `html/`). Open e.g. `figures/chapters/figure-3-1-architecture.html` in a browser without the thesis markdown viewer.

## Where they appear in the manuscript

| Location | Numbering | Role |
|----------|-----------|------|
| **Chapter 3** (`Chapter3_System_Design.md`) | Figure 3.1–3.6 | Architecture, data stores, dual-plane, GraphRAG, chat pipeline, sequence |
| **Chapter 4** (`Chapter4_Implementation.md`) | Figure 4.1–4.2 | Ingestion pipeline, frontend routes |
| **Chapter 5** (`Chapter5_Results_and_Evaluation.md`) | Figure 5.1–5.3 | Metric separation, claim filter progression, vignette eval |
| **Appendix A** (`Appendix_A_Figures_and_Diagrams.md`) | Figure A.1–A.8, Table A.1–A.2 | Full catalog (same content as Ch.3–4 tables 3.1 / 4.1) |

Chapters embed `chapters/figure-*.html`, which point at the same `html/*.html` Archify viewers; only the **caption number** changes (3.x / 4.x / 5.x vs A.x).

## File map

| Chapter wrapper | Archify HTML | Appendix | Chapter |
|-----------------|--------------|----------|---------|
| `chapters/figure-3-1-architecture.html` | `figure-a1-architecture.html` | A.1 | **3.1** |
| `chapters/figure-3-2-datastores.html` | `figure-a5-datastores.html` | A.5 | **3.2** |
| `chapters/figure-3-3-dual-plane.html` | `figure-a8-dual-plane.html` | A.8 | **3.3** |
| `chapters/figure-3-4-graphrag.html` | `figure-a4-graphrag.html` | A.4 | **3.4** |
| `chapters/figure-3-5-chat-workflow.html` | `figure-a2-chat-workflow.html` | A.2 | **3.5** |
| `chapters/figure-3-6-chat-sequence.html` | `figure-a7-chat-sequence.html` | A.7 | **3.6** |
| `chapters/figure-4-1-kb-pipeline.html` | `figure-a3-kb-pipeline.html` | A.3 | **4.1** |
| `chapters/figure-4-2-frontend-routes.html` | `figure-a6-frontend-routes.html` | A.6 | **4.2** |
| `chapters/figure-5-1-eval-metrics-split.html` | `figure-5-1-eval-metrics-split.html` | — | **5.1** |
| `chapters/figure-5-2-claim-filter-progression.html` | `figure-5-2-claim-filter-progression.html` | — | **5.2** |
| `chapters/figure-5-3-vignette-eval.html` | `figure-5-3-vignette-eval.html` | — | **5.3** |

Styles: `thesis-figures.css` (markdown embeds), `chapter-figure-page.css` (standalone chapter pages).

## Static images (Word / PDF)

Markdown iframes work in browsers and some static-site exports. For Word or LaTeX:

1. Open the `.html` file in a browser (pan/zoom as needed).
2. Use Archify’s export/share from the viewer toolbar, or print to PDF and crop.
3. Save PNGs under `figures/png/` (e.g. `figure-3-1-architecture.png`) and reference with `![Figure 3.1](figures/png/figure-3-1-architecture.png)` if your toolchain does not support HTML.

## Regenerate

```powershell
$archify = "$env:USERPROFILE\.agents\skills\archify\bin\archify.mjs"
$fig = "c:\Users\VinhNgo\hf_cdss\thesis\figures"
node $archify deliver architecture "$fig\archify\figure-a1-architecture.json" "$fig\html\figure-a1-architecture.html" --quality showcase
node $archify deliver dataflow "$fig\archify\figure-5-1-eval-metrics-split.json" "$fig\html\figure-5-1-eval-metrics-split.html" --quality showcase
# … other pairs in archify/
```

Edit the `.json` spec first, then `deliver` overwrites the matching HTML. Re-run the chapter wrapper generator in `chapters/` only if captions or paths change (wrappers are plain HTML, not Archify output).
