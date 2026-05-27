"""Domain Agent — loads domain-specific prompt pack for downstream agents."""

DOMAIN_PACKS: dict[str, dict] = {
    "finance": {
        "kpis": ["MRR", "ARR", "Gross Margin", "Churn Rate", "CAC", "LTV", "Runway", "AR Aging"],
        "vocab": ["revenue", "COGS", "MRR", "ARR", "churn", "cohort", "gross margin", "net margin", "runway", "AR aging"],
        "cleaning_hints": "Treat negative revenue as refunds. Flag AR aging > 90 days as outlier.",
        "analysis_hints": "Always include MoM and YoY comparisons. Prioritize cash metrics over accrual.",
    },
    "healthcare": {
        "kpis": ["Patient Volume", "Readmission Rate", "Length of Stay", "Episode of Care", "Bed Occupancy"],
        "vocab": ["patient", "episode", "readmission", "ICD-10", "CPT", "length of stay", "discharge", "admission"],
        "cleaning_hints": "Flag readmission within 30 days. Validate ICD-10 and CPT code formats.",
        "analysis_hints": "Segment by payer type. Highlight readmission rate versus benchmark.",
    },
    "retail": {
        "kpis": ["AOV", "Repeat Purchase Rate", "Inventory Turn", "Return Rate", "SKU Margin", "Channel Attribution"],
        "vocab": ["SKU", "AOV", "repeat purchase", "inventory turn", "return rate", "channel", "CAC", "LTV"],
        "cleaning_hints": "Flag negative inventory quantities. Treat returns as negative revenue.",
        "analysis_hints": "Segment by channel and SKU. Highlight top/bottom performers by margin.",
    },
    "marketing": {
        "kpis": ["CTR", "CPA", "CAC", "LTV", "ROAS", "Attribution Window"],
        "vocab": ["CTR", "CPA", "CAC", "LTV", "ROAS", "impressions", "clicks", "conversions", "attribution"],
        "cleaning_hints": "Flag CTR > 30% as anomalous. Validate that CPA is positive.",
        "analysis_hints": "Always compare channel efficiency by CPA. Show funnel conversion rates.",
    },
    "operations": {
        "kpis": ["Throughput", "Cycle Time", "OEE", "Defect Rate", "Lead Time"],
        "vocab": ["throughput", "cycle time", "OEE", "defect", "lead time", "capacity", "utilization"],
        "cleaning_hints": "Flag zero cycle times. Validate throughput is non-negative.",
        "analysis_hints": "Highlight bottlenecks. Compare actual vs target throughput.",
    },
    "other": {
        "kpis": [],
        "vocab": [],
        "cleaning_hints": "Apply standard data quality rules.",
        "analysis_hints": "Use generic aggregations (sum, mean, count, distinct).",
    },
}


class DomainAgent:
    """Loads the domain prompt pack and exposes it to all downstream agents."""

    def get_pack(self, domain: str) -> dict:
        return DOMAIN_PACKS.get(domain, DOMAIN_PACKS["other"])

    def build_system_prompt(self, domain: str) -> str:
        pack = self.get_pack(domain)
        kpi_str = ", ".join(pack["kpis"]) if pack["kpis"] else "generic metrics"
        vocab_str = ", ".join(pack["vocab"]) if pack["vocab"] else "standard business terms"
        return (
            f"You are a data intelligence agent specializing in the {domain} domain. "
            f"Key KPIs for this domain: {kpi_str}. "
            f"Domain vocabulary: {vocab_str}. "
            f"Cleaning guidance: {pack['cleaning_hints']} "
            f"Analysis guidance: {pack['analysis_hints']}"
        )
