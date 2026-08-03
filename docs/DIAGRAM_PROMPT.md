# Diagram Generation Prompts (Templates & Examples)

Purpose
-------
This file contains short, copy‑pasteable prompt templates and examples for generating diagrams of computational pipelines, model architectures, and data flows. Use these with diagram tools (Mermaid, Graphviz) or image-generation models (SVG/PNG outputs).

General guidance
----------------
- State the diagram type (flowchart, data schema, model architecture).
- Specify required labels, node shapes, and edge directions.
- Provide desired visual style: color palette, layout (left-to-right / top-to-bottom), font size, and file format (SVG preferred for publication).
- Ask for accessible colors and include a brief caption.

Mermaid flowchart (pipeline) — prompt template
--------------------------------------------
"Create a left-to-right flowchart describing the data-processing pipeline. Nodes: Raw images → Panel harmonisation → Normalisation (GMM) → Geometry conversion → Graph construction (r=30μm, k=10) → Spatial features → Model assembly → LOCO evaluation. Include brief one-line notes beneath each node. Output as a Mermaid flowchart code block and an SVG file suitable for publication. Use a muted color palette and annotate key parameters (r=30 μm, k=10, k-means k=15)."

Example Mermaid snippet
-----------------------
```mermaid
flowchart LR
  A[Raw images] --> B[Panel harmonisation]
  B --> C[Normalisation\n(percentile + GMM)]
  C --> D[Geometry conversion\n(px → μm)]
  D --> E[Graph construction\n(r=30μm, k=10)]
  E --> F[Spatial features\n(nb_mean, nb_std)]
  F --> G[Model assembly & LOCO]
```

Image-generation (publication figure) — prompt template
-----------------------------------------------------
"Create a publication-ready, vector SVG of the pipeline with left-to-right flow. Use distinct icons for imaging, tables, compute, and plots. Label each step and include parameter callouts (r=30 μm, k=10). Use a professional, muted color palette (blues/greys), 1200px width, and ensure text is editable as SVG. Provide a short caption suitable for a figure legend."

Model architecture diagram — prompt template
-----------------------------------------
"Draw a block diagram of the classifier pipeline: feature input (per-cell markers, spatial aggregates) → preprocessing (imputer/scaler) → HistGradientBoostingClassifier (show key hyperparameters) → evaluation (LOCO). Indicate shapes and dimensions of tensors or tables where appropriate."

Tips for using LLMs or image models
-----------------------------------
- Prefer SVG/vector output when possible for publication edits.
- Provide example colors or a hex palette to avoid guesswork.
- If using an image-only model, request a high-resolution PNG (300 DPI) and include alt text for accessibility.

Short checklist to include in prompts
-----------------------------------
- Diagram type
- Layout direction
- Nodes and short labels
- Critical parameter annotations
- Output format (SVG/PNG)
- Color palette and accessibility note
