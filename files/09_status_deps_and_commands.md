11. Implementation Status Checklist
Item	Status
✅	pipeline2/config.py — declarative registry, 6 cohorts + Danenberg spec	done
✅	pipeline2/loaders.py — one generic loader, no cohort branching	done
✅	pipeline2/acquire/ — download + extraction scripts, incl. sorin_extract.py	done
✅	Stage 0 s0_audit.py → GATE 0 PASS	done
✅	Stage 0b s0b_markers.py + panel/*.csv → GATE 0b PASS (5/5 checks)	done
✅	Stage 1 s1_values.py + nn/marker_encoder.py → GATE 1 PASS, winner V3	done
✅	Stage 1b s1b_labels.py + panel/gate1b_expect.csv → GATE 1b PASS (7/7, stroma waived)	done
✅	_validation/extract_hand_mapping.py + hand_mapping_reference.csv	done, retained
✅	Plan file updated with Stage 1b result, the waiver, and all three known gaps	done
🟡	Stage 2 s2_tokens.py + nn/tokens.py → GATE 2	designed, not written, not confirmed
⚪	Stage 3 s3_encoder.py → GATE 3	planned
❌	Stage 4 s4_spatial.py	DEFERRED (D-18)
❌	Stage 5 global slide branch	DROPPED (D-19)
⚪	Stage 6 s6_train.py → GATE 6	planned
⚪	Stage 7 s7_eval.py → GATE 7	planned
⚪	Danenberg arrival test (D-24) — run the unchanged pipeline on a 7th cohort	planned, after Stage 7 or as a standalone demo
⚪	Ablation: do co-expression + log-prevalence earn their place? (§7 gap 1)	not run
⚪	Re-test the nesting layer (§7 gap 2)	not run
⚪	Wire up or delete --evidence-sweep / --graph-check (§7 gap 3)	not done
12. Dependencies
Package	Purpose	Status
requests	HGNC + UniProt REST in Stage 0b. Used once, then the cached work/marker_registry.csv makes every later run offline. Kaggle has internet off by default, so the cache is not optional	installed
networkx	The Stage 1b nesting DAG, SCC contraction, acyclicity assert	installed
leidenalg	No longer used — Leiden was replaced by scipy.cluster.hierarchy average linkage (D-22)	installed but unused
scipy	cluster.hierarchy.linkage/fcluster, spatial.distance.squareform, optimize.linear_sum_assignment, stats.rankdata	installed
torch 2.12.0+cpu	Stages 1, 2, 3, 6	installed, no CUDA
pandas, numpy, matplotlib (Agg)	throughout	installed
sentence-transformers (~90 MB)	Optional, naming only. α = 0, so the pipeline runs correctly without it	not required
torch_geometric	Not needed — Stage 4 uses plain scatter ops, and it is not available on Kaggle by default	not installed, by design
13. Verification Commands

python pipeline2/s0_audit.py --all              # gate 0  : counts + tissue plots
python pipeline2/s0b_markers.py --resolve       # gate 0b : HGNC/UniProt resolution + review queue
python pipeline2/s0b_markers.py --offline       # gate 0b : must reproduce byte-identically
python pipeline2/s1_values.py  --bakeoff        # gate 1  : V1 vs V2a vs V2b vs V3, scored LOCO
python pipeline2/s1b_labels.py                  # gate 1b : all 7 checks in one report
#   NOTE: --evidence-sweep and --graph-check are accepted but currently DO NOTHING - every run
#   emits the full report. See section 7, gap 3.
python pipeline2/s2_tokens.py  --check          # gate 2  : reconstruction R2 vs median   [NOT BUILT]
python pipeline2/s3_encoder.py --lambda-sweep   # gate 3  : LOCO F1 + retained bits (fresh probe)
# python pipeline2/s4_spatial.py --ablate       # gate 4  : DEFERRED - not built this pass
python pipeline2/s6_train.py   --ablate-losses  # gate 6  : 2 vs 4 losses, prototype drift
python pipeline2/s7_eval.py --loco --frozen-test ferguson   # gate 7
Other useful commands:


python _validation/extract_hand_mapping.py      # regenerate the Gate 1b scoring set from git
python pipeline2/s1_values.py --rebuild         # rebuild value tables from scratch
git show HEAD:pipeline/step4_labels.py          # the old hand-written ontology (T and NAT dicts)
git show HEAD:pipeline/panel/never_merge.csv    # the 9 look-alike pairs
git show HEAD:kaggle/INSTRUCTIONS.md            # the old Kaggle path
