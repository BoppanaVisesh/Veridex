// ======================== constants.js ========================
// Shared constants used across all pages

const DT = {
  D1:{label:'Listing Readiness Risk',icon:'🚨',urgency:'P0',sla:'SAME-DAY',desc:'Product aging without complete/validated data before publish deadline. Expedite enrichment and validation.'},
  D2:{label:'Category/Channel Placement',icon:'📂',urgency:'P1',sla:'3D',desc:'Best catalog category and sales channel placement for product given validated technical attributes.'},
  D3:{label:'Data Decay Risk',icon:'⚡',urgency:'P0',sla:'SAME-DAY',desc:'Product data going stale or contradicted by newer source updates. Reconcile conflicting vendor feeds.'},
  D4:{label:'Re-validation Cycle',icon:'🔄',urgency:'P1',sla:'3D',desc:'Product data due for periodic re-verification audit. Refresh specs, verify plausibility, and check drift.'},
  D5:{label:'Incomplete Listing Promotion',icon:'💡',urgency:'P2',sla:'14D',desc:'High-demand low-completeness product needs prioritized 3-tier enrichment to unblock publication.'},
  D6:{label:'Source Reliability Health',icon:'📊',urgency:'P1',sla:'3D',desc:'Supplier upload feed showing declining validation ratio. Quarantine failing batches and re-map schema.'},
  D7:{label:'Certification/Compliance Gap',icon:'🔒',urgency:'P0',sla:'SAME-DAY',desc:'Product missing required certification or unverifiable compliance. Hard compliance veto required.'},
  D8:{label:'Publish-Confidence Threshold',icon:'🎯',urgency:'P2',sla:'14D',desc:'Evaluate whether specific field confidence is high enough to publish as-is without manual review.'},
  D9:{label:'Catalog Expansion Opportunity',icon:'🚀',urgency:'P3',sla:'21D',desc:'Fully validated product qualifies for multi-channel partner marketplace syndication expansion.'},
};

const AGENTS = [
  {k:'crm',    lbl:'Catalog Database Agent',   model:'Gemini Flash',        t:142},
  {k:'email',  lbl:'Supplier Ingest Agent',     model:'Gemini Pro',          t:318},
  {k:'meetings',lbl:'Channel Partner Agent',    model:'Gemini Pro',          t:401},
  {k:'activity',lbl:'Validation Engine Agent',  model:'Gemini Flash',        t:96},
  {k:'kb',     lbl:'Enrichment & Taxonomy',     model:'Gemini Flash',        t:78},
  {k:'market', lbl:'Marketplace Feed Agent',    model:'Gemini Flash',        t:612},
  {k:'compliance',lbl:'Compliance Registry',    model:'Deterministic',       t:24},
  {k:'precedent',lbl:'Precedent (Vector)',      model:'text-embedding-004',  t:88},
];

const BIDDER_META = {
  Revenue:        {model:'Gemini Pro',       col:'#2563EB'},
  Risk:           {model:'Gemini Pro',       col:'#DC2626'},
  CustomerSuccess:{model:'Gemini Pro',       col:'#16A34A'},
  Finance:        {model:'Gemini Flash',     col:'#D97706'},
  Ops:            {model:'Gemini Flash',     col:'#7C3AED'},
  Compliance:     {model:'Deterministic',    col:'#0F172A'},
};

const BIDDER_ORDER = ['Revenue','Risk','CustomerSuccess','Finance','Ops','Compliance'];

const PIPELINE_STAGES = ['Planner','Evidence','DRE','Detect','Bidding','Optimizer','Explain','Review'];
