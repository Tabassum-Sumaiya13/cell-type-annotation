"""
STEP 4 - Label ontology.

Builds the hand-mapped Cell Ontology (CL) table (open item O2) and applies it.
Encodes the decision framework: type vs state (Q4), drop QC failures (Q1), keep ambiguous
real cells flagged (Q1/A10), gold rules (A12/A13).

Outputs:
  harmonised/_audit/cl_mapping.csv       the mapping table (deliverable, auditable)
  harmonised/_audit/ontology_tree.csv    child -> parent DAG for the hierarchical loss
  harmonised/{cohort}_labels.parquet     per cell: native, cl_id, cl_name, L1, L2, state,
                                          keep, ambiguous, label_confidence, is_gold
  harmonised/_audit/step4_report.md
"""
import numpy as np, pandas as pd, os
from common import COHORTS, DATASETS, OUT, AUDIT, load_geometry

# ---------------------------------------------------------------- target catalogue
# key -> (CL id, CL name, L1, L2)   L2=None means "coarse, not scorable at the 9-class level"
T = {
 'CD4T':('CL:0000624','CD4+ T cell','Immune','T cell'),
 'CD8T':('CL:0000625','CD8+ T cell','Immune','T cell'),
 'Treg':('CL:0000815','regulatory T cell','Immune','T cell'),
 'Tcell':('CL:0000084','T cell','Immune','T cell'),
 'B':('CL:0000236','B cell','Immune','B/Plasma'),
 'Plasma':('CL:0000786','plasma cell','Immune','B/Plasma'),
 'Mac':('CL:0000235','macrophage','Immune','Myeloid'),
 'M1':('CL:0000863','inflammatory macrophage','Immune','Myeloid'),
 'M2':('CL:0000890','alternatively activated macrophage','Immune','Myeloid'),
 'Mono':('CL:0000576','monocyte','Immune','Myeloid'),
 'DC':('CL:0000451','dendritic cell','Immune','Myeloid'),
 'APC':('CL:0000145','antigen presenting cell','Immune','Myeloid'),
 'Neut':('CL:0000775','neutrophil','Immune','Granulocyte'),
 'Gran':('CL:0000094','granulocyte','Immune','Granulocyte'),
 'NK':('CL:0000623','natural killer cell','Immune','NK'),
 'ImmOther':('CL:0000738','leukocyte','Immune',None),
 'MyeloidMix':('CL:0000766','myeloid leukocyte','Immune',None),
 'Endo':('CL:0000115','endothelial cell','Stromal','Endothelial'),
 'Lymph':('CL:0002138','endothelial cell of lymphatic vessel','Stromal','Endothelial'),
 'Fib':('CL:0000057','fibroblast','Stromal','Fibroblast/Muscle'),
 'SMC':('CL:0000192','smooth muscle cell','Stromal','Fibroblast/Muscle'),
 'Mesen':('CL:0000134','mesenchymal cell','Stromal','Fibroblast/Muscle'),
 'StromaFib':('CL:0000499','stromal cell','Stromal','Fibroblast/Muscle'),
 'StromaGen':('CL:0000499','stromal cell','Stromal',None),
 'ICC':('CL:0002088','interstitial cell of Cajal','Stromal','Other'),
 'Nerve':('CL:0000540','neuron','Stromal','Other'),
 'Adip':('CL:0000136','adipocyte','Stromal','Other'),
 'Tumor':('CL:0001063','neoplastic cell','Epithelial/Tumour','Epithelial/Tumour'),
 'Entero':('CL:0000584','enterocyte','Epithelial/Tumour','Epithelial/Tumour'),
 'Goblet':('CL:0000160','goblet cell','Epithelial/Tumour','Epithelial/Tumour'),
 'Paneth':('CL:0000510','paneth cell','Epithelial/Tumour','Epithelial/Tumour'),
 'NEndo':('CL:0000164','enteroendocrine cell','Epithelial/Tumour','Epithelial/Tumour'),
 'TA':('CL:0009011','transit amplifying cell','Epithelial/Tumour','Epithelial/Tumour'),
 'DROP':(None,'(dropped)',None,None),
}

# ---------------------------------------------------------------- native -> (target, state, keep, ambiguous)
# state = biological state kept separate from type (Q4). keep=False drops from labelled set.
NAT = {
 'CRC': {
  'B cells':('B',None,1,0),'CD11b+ monocytes':('Mono',None,1,0),
  'CD11b+CD68+ macrophages':('Mac',None,1,0),'CD11c+ DCs':('DC',None,1,0),
  'CD163+ macrophages':('Mac',None,1,0),'CD3+ T cells':('Tcell',None,1,0),
  'CD4+ T cells':('CD4T',None,1,0),'CD4+ T cells CD45RO+':('CD4T','CD45RO+',1,0),
  'CD4+ T cells GATA3+':('CD4T','GATA3+',1,0),'CD68+ macrophages':('Mac',None,1,0),
  'CD68+ macrophages GzmB+':('Mac','GzmB+',1,0),'CD68+CD163+ macrophages':('Mac',None,1,0),
  'CD8+ T cells':('CD8T',None,1,0),'NK cells':('NK',None,1,0),'Tregs':('Treg',None,1,0),
  'adipocytes':('Adip',None,1,0),'dirt':('DROP',None,0,0),'granulocytes':('Gran',None,1,0),
  'immune cells':('ImmOther',None,1,0),'immune cells / vasculature':('DROP',None,0,1),
  'lymphatics':('Lymph',None,1,0),'nerves':('Nerve',None,1,0),'plasma cells':('Plasma',None,1,0),
  'smooth muscle':('SMC',None,1,0),'stroma':('StromaFib',None,1,0),'tumor cells':('Tumor',None,1,0),
  'tumor cells / immune cells':('DROP',None,0,1),'undefined':('DROP',None,0,0),
  'vasculature':('Endo',None,1,0),
 },
 'HubMap': {
  'B':('B',None,1,0),'CD4+ T cell':('CD4T',None,1,0),'CD57+ Enterocyte':('Entero','CD57+',1,0),
  'CD66+ Enterocyte':('Entero','CD66+',1,0),'CD7+ Immune':('ImmOther','CD7+',1,0),
  'CD8+ T':('CD8T',None,1,0),'Cycling TA':('TA','cycling',1,0),'DC':('DC',None,1,0),
  'Endothelial':('Endo',None,1,0),'Enterocyte':('Entero',None,1,0),'Goblet':('Goblet',None,1,0),
  'ICC':('ICC',None,1,0),'Lymphatic':('Lymph',None,1,0),'M1 Macrophage':('M1',None,1,0),
  'M2 Macrophage':('M2',None,1,0),'MUC1+ Enterocyte':('Entero','MUC1+',1,0),'NK':('NK',None,1,0),
  'Nerve':('Nerve',None,1,0),'Neuroendocrine':('NEndo',None,1,0),'Neutrophil':('Neut',None,1,0),
  'Paneth':('Paneth',None,1,0),'Plasma':('Plasma',None,1,0),'Smooth muscle':('SMC',None,1,0),
  'Stroma':('StromaFib',None,1,0),'TA':('TA',None,1,0),
 },
 'Keren': {
  'B':('B',None,1,0),'CD3_T':('Tcell',None,1,0),'CD4_T':('CD4T',None,1,0),'CD8_T':('CD8T',None,1,0),
  'DC':('DC',None,1,0),'DC_Mono':('MyeloidMix',None,1,0),'Endothelial':('Endo',None,1,0),
  'Keratin_positive_tumor':('Tumor','keratin+',1,0),'Macrophages':('Mac',None,1,0),
  'Mesenchymal_like':('Mesen',None,1,0),'Mono_Neu':('MyeloidMix',None,1,0),'NK':('NK',None,1,0),
  'Neutrophils':('Neut',None,1,0),'Other_immune':('ImmOther',None,1,0),'Tregs':('Treg',None,1,0),
  'Tumor':('Tumor','keratin-',1,0),'Unidentified':('DROP',None,0,0),
 },
 'UPMC': {
  'APC':('APC',None,1,0),'B cell':('B',None,1,0),'CD4 T cell':('CD4T',None,1,0),
  'CD8 T cell':('CD8T',None,1,0),'Granulocyte':('Gran',None,1,0),'Lymph vessel':('Lymph',None,1,0),
  'Macrophage':('Mac',None,1,0),'Naive immune cell':('ImmOther','naive',1,0),
  'Stromal / Fibroblast':('Fib',None,1,0),'Tumor':('Tumor',None,1,0),
  'Tumor (CD15+)':('Tumor','CD15+',1,0),'Tumor (CD20+)':('Tumor','CD20+',1,0),
  'Tumor (CD21+)':('Tumor','CD21+',1,0),'Tumor (Ki67+)':('Tumor','Ki67+',1,0),
  'Tumor (Podo+)':('Tumor','Podo+',1,0),'Vessel':('Endo',None,1,0),
 },
 'ferguson': {
  'immune':('ImmOther',None,1,0),'stromal':('StromaGen',None,1,0),'tumour':('Tumor',None,1,0),
 },
}

# ---------------------------------------------------------------- DAG (child -> parent) for hierarchical loss
TREE = [
 ('root','root'),
 ('Immune','root'),('Stromal','root'),('Epithelial/Tumour','root'),
 ('T cell','Immune'),('B/Plasma','Immune'),('Myeloid','Immune'),('NK','Immune'),
 ('Granulocyte','Immune'),
 ('Endothelial','Stromal'),('Fibroblast/Muscle','Stromal'),('Other','Stromal'),
 # leaves under L2
 ('CD4+ T cell','T cell'),('CD8+ T cell','T cell'),('regulatory T cell','T cell'),('T cell (generic)','T cell'),
 ('B cell','B/Plasma'),('plasma cell','B/Plasma'),
 ('macrophage','Myeloid'),('inflammatory macrophage','Myeloid'),('alternatively activated macrophage','Myeloid'),
 ('monocyte','Myeloid'),('dendritic cell','Myeloid'),('antigen presenting cell','Myeloid'),
 ('neutrophil','Granulocyte'),('granulocyte (generic)','Granulocyte'),
 ('natural killer cell','NK'),
 ('endothelial cell','Endothelial'),('endothelial cell of lymphatic vessel','Endothelial'),
 ('fibroblast','Fibroblast/Muscle'),('smooth muscle cell','Fibroblast/Muscle'),('mesenchymal cell','Fibroblast/Muscle'),
 ('interstitial cell of Cajal','Other'),('neuron','Other'),('adipocyte','Other'),
 ('neoplastic cell','Epithelial/Tumour'),('enterocyte','Epithelial/Tumour'),('goblet cell','Epithelial/Tumour'),
 ('paneth cell','Epithelial/Tumour'),('enteroendocrine cell','Epithelial/Tumour'),('transit amplifying cell','Epithelial/Tumour'),
]

def build_mapping_table():
    rows=[]
    for coh, m in NAT.items():
        for nat,(key,state,keep,amb) in m.items():
            cl_id,cl_name,L1,L2 = T[key]
            rows.append(dict(cohort=coh, native_label=nat, target=key, cl_id=cl_id, cl_name=cl_name,
                             L1=L1, L2=(L2 or ''), state=(state or ''), keep=bool(keep), ambiguous=bool(amb)))
    mp = pd.DataFrame(rows)
    mp.to_csv(os.path.join(AUDIT,'cl_mapping.csv'), index=False)
    pd.DataFrame(TREE, columns=['node','parent']).drop_duplicates().to_csv(
        os.path.join(AUDIT,'ontology_tree.csv'), index=False)
    return mp

def native_and_conf(cohort):
    """native label + per-cell confidence + donor, aligned to geometry cell_id order."""
    D=DATASETS
    if cohort=='CRC':
        s=pd.read_csv(os.path.join(D,'CRC','CRC_clusters_neighborhoods_markers.csv'),usecols=['ClusterName'])
        return s.ClusterName.values, np.ones(len(s)), None
    if cohort=='HubMap':
        base=pd.read_parquet(os.path.join(D,'HubMap','cell_locations.parquet'),columns=['cell_id'])
        lab=pd.read_parquet(os.path.join(D,'HubMap','cell_labels.parquet'),columns=['cell_id','Cell Type','unique_region'])
        lab=base.merge(lab,on='cell_id',how='left')
        donor=lab.unique_region.str.split('_').str[0].values
        return lab['Cell Type'].values, np.ones(len(lab)), donor
    if cohort=='Keren':
        s=pd.read_csv(os.path.join(D,'Keren','cell_locations.csv'),usecols=['cluster_label'])
        return s.cluster_label.values, np.ones(len(s)), None
    if cohort=='UPMC':
        s=pd.read_csv(os.path.join(D,'UPMC','dataset_info','cell_locations_and_labels.csv'),
                      usecols=['CLUSTER_LABEL','kNN.prob'])
        return s.CLUSTER_LABEL.values, s['kNN.prob'].values, None
    if cohort=='ferguson':
        s=pd.read_csv(os.path.join(D,'ferguson','cell_locations.csv'),usecols=['cluster_label'])
        return s.cluster_label.values, np.ones(len(s)), None

GOLD_CONF = {'UPMC':0.7}
HUBMAP_GOLD_DONORS = {'B004','B005','B006'}

def apply_cohort(cohort, mp):
    geo = load_geometry(cohort)[['cell_id']]
    nat, conf, donor = native_and_conf(cohort)
    assert len(nat)==len(geo), f"{cohort} native/geometry length mismatch"
    m = mp[mp.cohort==cohort].set_index('native_label')
    def col(field): return pd.Series(nat).map(m[field]).values
    out = pd.DataFrame({'cell_id':geo.cell_id.values, 'native_label':nat,
        'cl_id':col('cl_id'), 'cl_name':col('cl_name'), 'L1':col('L1'),
        'L2':col('L2'), 'state':col('state'),
        'keep':col('keep').astype(bool), 'ambiguous':col('ambiguous').astype(bool),
        'label_confidence':conf.astype('float32')})
    # gold: kept, not ambiguous, confident, and (HubMap) human-verified donor
    gold = out.keep & (~out.ambiguous)
    if cohort in GOLD_CONF:
        gold &= conf >= (GOLD_CONF[cohort] - 1e-6)   # float64 compare + eps: keep exactly-0.70 cells
    if cohort=='HubMap':
        gold &= pd.Series(donor).isin(HUBMAP_GOLD_DONORS).values
    out['is_gold']=gold.values
    out.to_parquet(os.path.join(OUT,f"{cohort}_labels.parquet"), index=False)
    return out

def main():
    mp = build_mapping_table()
    rep=["# STEP 4 - Label ontology report\n",
         f"Mapping table: `cl_mapping.csv` ({len(mp)} native labels). DAG: `ontology_tree.csv`.\n"]
    summ=[]
    for c in COHORTS:
        o=apply_cohort(c, mp)
        dropped=(~o.keep).sum(); amb=o.ambiguous.sum(); gold=o.is_gold.sum()
        summ.append(dict(cohort=c, cells=len(o), dropped=int(dropped),
                         ambiguous=int(amb), gold=int(gold),
                         L1_classes=o.loc[o.keep,'L1'].nunique(),
                         L2_classes=o.loc[o.keep & (o.L2!=''),'L2'].nunique()))
        print(f"[{c:8s}] {len(o):>9,}  drop {int(dropped):>6,}  gold {int(gold):>9,}")
    t=pd.DataFrame(summ)
    rep.append("## Per-cohort\n"+t.to_markdown(index=False)+"\n")
    # class distribution at L2 (gold only) pooled
    frames=[pd.read_parquet(os.path.join(OUT,f"{c}_labels.parquet"),columns=['cohort_dummy'] ) if False else None for c in []]
    rep.append("\n## L2 class counts (gold cells) per cohort\n")
    for c in COHORTS:
        o=pd.read_parquet(os.path.join(OUT,f"{c}_labels.parquet"))
        vc=o[o.is_gold & (o.L2!='')].L2.value_counts()
        rep.append(f"**{c}**: "+", ".join(f"{k} {v:,}" for k,v in vc.items())+"\n")
    open(os.path.join(AUDIT,'step4_report.md'),'w',encoding='utf-8').write("\n".join(rep))
    print("\n"+t.to_string(index=False))
    print("\nwrote cl_mapping.csv, ontology_tree.csv, {cohort}_labels.parquet, step4_report.md")

if __name__=='__main__':
    main()
