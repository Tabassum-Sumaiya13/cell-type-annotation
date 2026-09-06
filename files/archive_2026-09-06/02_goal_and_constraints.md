1. Project Goal and Framing
Objective. Give every cell in a spatial-proteomics tissue image a cell-type name (T cell, tumour cell, fibroblast…) with a model that still works on a cohort it has never seen — a different hospital, a different machine, a different antibody panel. The model must say "unknown" rather than guess when it should not be confident.

Deliverable shape. One model trained on cancer cohorts across 3 imaging technologies (CODEX, MIBI-TOF, IMC), annotating cells on a held-out cohort zero-shot.

Thesis framing. The central scientific claim is that label harmonisation across cohorts can be learned from marker profiles instead of hand-written into a fixed ontology. Stage 1b is the experiment that proves or kills this claim. It passed.

Working method (non-negotiable). Every stage has a concrete pass/fail gate declared before the run. Nothing proceeds until its gate passes. Each stage produces exactly one markdown report in reports/, written for a reader rather than as a log.

2. Permanent Constraints
2.1 Research constraints
Constraint	Detail
Cancer datasets only	No healthy tissue. Datasets/HubMap/ exists on disk but is not used — healthy tissue, different label space, 2.6M cells would swamp the rest. Leave the folder alone.
ferguson is frozen	Test-only holdout. Never trained on. One final number, once.
No fixed Cell Ontology	No CL:0000084 anywhere in the pipeline. No hand-written per-cohort label dictionary. This is the whole point of the rebuild.
No string matching of marker names	Marker identity comes from HGNC/UniProt resolution to a stable triple key, cached.
No text in the label distance	α = 0. Text may only name clusters, and only as a fallback after marker-based naming.
Every stage gated	Concrete pass/fail check, declared in advance, reported in reports/sN_*.md.
Declared-before-run assertions	Gate expectations live in CSV files (panel/gate1_expect.csv, panel/gate1b_expect.csv) committed before the run, so results cannot be judged after the fact.
2.2 Data constraints
Sorin arrives uint8 (0–255), already display-quantised where real IMC is 16-bit. Causes heavy zero-inflation and rank ties. This has already broken one design (see §6.3, correction 3).
Keren arrives z-scored; UPMC arrives arcsinh; CRC, Phillips, ferguson arrive raw. Four different curve shapes into one encoder.
Sorin has only 17 usable protein markers — the panel-mismatch stress test.
No fibroblast-specific marker exists anywhere in the roster. No PDGFRB, FAP, COL1A1, DCN, LUM, POSTN, S100A4, TAGLN. ACTA2 is CRC+UPMC only; CD34 is CRC+Phillips+UPMC only. This is a permanent, measured data limitation (see §6.4).
No cohort ships images or masks except Sorin (which needed feature extraction written). image_id is a column, not a file. All work is dataframe work, zero pixels.
All coordinate frames are image-local (CRC's are even tile-local, X 0–1919 ≈ 724 µm). Any kNN graph must be built inside one image.
2.3 Computational constraints
Local development: torch 2.12.0+cpu, no CUDA, 13.8 GB RAM, 8 cores. Full scale will not finish here.
Development subsample: ~40k cells per cohort (~240k total), stratified by patient × native label, cell ids saved so runs reproduce. Every gate is checkable at this scale.
Final run: Kaggle T4/P100 with all ~4.9M cells. The old repo has a Kaggle path (git show HEAD:kaggle/INSTRUCTIONS.md) but it says "Accelerator: None" for the old tree model — the new one needs the GPU turned on.
Kaggle quota 30 h/week. Checkpoint every epoch; the LOCO loop must resume fold by fold.
Kaggle has internet off by default — the cached work/marker_registry.csv is therefore not optional.
First-pass model size chosen to fit CPU development: d_model = 128, 2 attention blocks, 4 heads, 16-d marker value embedding, 2 message-passing layers.
2.4 Communication constraints (user preferences, permanent)
Plain simple English. Explain any technical term the first time. English is the user's second language.
Short sentences, short paragraphs, bullet points where they help.
Confirm before every run and every decision.
One report per work item. No jargon.
Programming answers follow: what is wrong → why → best fix → corrected code → side effects.
Recommend the best solution, not a menu of options. Challenge the user's approach when there is a better one.
2.5 Session/tooling constraints
Do not call the Agent tool unless the user requests it.
Do not use workflows or deep-research unless the user requests it.
Windows 11, PowerShell primary shell, Bash tool also available.
MCP servers claude.ai Gmail, Google Calendar, Google Drive require OAuth that cannot be run in this session — unavailable until the user authorises them via claude.ai connector settings.
2.6 Reviewer expectations already surfaced
Three critiques were raised and answered on 2026-08-10 (full detail in §9 Decision Log entries D-14 to D-17):

"V2 FiLM overfits on Keren (43 slides)" — arithmetic corrected (40 slides, 4,942 cells/slide), risk accepted, fix strengthened, and FiLM subsequently lost the bake-off anyway.
"Directed containment is not transitive → cycles → force transitive closure" — gap accepted, diagnosis corrected, better fix (SCC contraction).
"A 1,750-way adversary can never fall to 0.06% — the gate will fail a working model" — the metric was defective; replaced with retained bits + LOCO F1 decision.
