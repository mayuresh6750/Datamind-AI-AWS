"""Supervisor Agent — orchestrates the full pipeline via LangGraph state machine."""
from typing import Any, TypedDict

import structlog

log = structlog.get_logger()


class PipelineState(TypedDict):
    dataset_id: str
    user_id: str
    job_id: str
    domain: str
    filenames: list[str]
    raw_rows: list[dict]
    column_profiles: list[dict]
    merge_plan: dict
    merge_decision: dict
    cleaning_plan: dict
    cleaning_decision: dict
    cleaned_rows: list[dict]
    audit_entries: list[dict]
    intent_question: str
    analysis_spec: dict
    numeric_results: list[dict]
    textual_results: list[dict]
    dashboard: dict
    error: str | None
    status: str


def build_pipeline_graph():
    """Build and return the LangGraph pipeline. Import lazily to avoid load-time cost."""
    try:
        from langgraph.graph import END, StateGraph
    except ImportError:
        log.warning("langgraph_not_available", msg="LangGraph not installed; pipeline graph unavailable.")
        return None

    from app.agents.cleaning_executor import CleaningExecutorAgent
    from app.agents.cleaning_plan import CleaningPlanAgent
    from app.agents.dashboard_agent import DashboardAgent
    from app.agents.domain import DomainAgent
    from app.agents.ingestion import IngestionAgent
    from app.agents.insights import InsightsAgent
    from app.agents.intent import IntentAgent
    from app.models.schemas import CleaningPlanDecision, ColumnProfile

    domain_agent = DomainAgent()
    ingestion_agent = IngestionAgent()
    cleaning_plan_agent = CleaningPlanAgent()
    cleaning_executor_agent = CleaningExecutorAgent()
    intent_agent = IntentAgent()
    dashboard_agent = DashboardAgent()
    insights_agent = InsightsAgent()

    graph = StateGraph(PipelineState)

    async def node_load_domain(state: PipelineState) -> dict:
        pack = domain_agent.get_pack(state["domain"])
        log.info("supervisor_domain_loaded", domain=state["domain"])
        return {"status": "domain_loaded"}

    async def node_ingest(state: PipelineState) -> dict:
        profiles = ingestion_agent.profile_columns(state["raw_rows"])
        file_profiles = [(state["dataset_id"], profiles)]
        merge_plan = ingestion_agent.propose_merge_plan(file_profiles)
        log.info("supervisor_ingestion_done", columns=len(profiles))
        return {
            "column_profiles": [p.model_dump() for p in profiles],
            "merge_plan": merge_plan.model_dump(),
            "status": "awaiting_hitl_merge",
        }

    async def node_await_merge_hitl(state: PipelineState) -> dict:
        return {"status": "awaiting_hitl_merge"}

    async def node_cleaning_plan(state: PipelineState) -> dict:
        from app.models.schemas import ColumnProfile
        profiles = [ColumnProfile(**p) for p in state["column_profiles"]]
        plan = await cleaning_plan_agent.propose(state["raw_rows"], profiles, state["domain"])
        log.info("supervisor_cleaning_plan_done", steps=len(plan.steps))
        return {"cleaning_plan": plan.model_dump(), "status": "awaiting_hitl_cleaning"}

    async def node_await_cleaning_hitl(state: PipelineState) -> dict:
        return {"status": "awaiting_hitl_cleaning"}

    async def node_execute_cleaning(state: PipelineState) -> dict:
        from app.models.schemas import CleaningPlanDecision, CleaningStep
        steps = [CleaningStep(**s) for s in state["cleaning_plan"]["steps"]]
        decision = CleaningPlanDecision(**state["cleaning_decision"])
        cleaned, audit = cleaning_executor_agent.execute(state["raw_rows"], steps, decision)
        log.info("supervisor_cleaning_executed", cleaned_rows=len(cleaned))
        return {"cleaned_rows": cleaned, "audit_entries": audit, "status": "executing"}

    async def node_intent(state: PipelineState) -> dict:
        from app.models.schemas import ColumnProfile
        profiles = [ColumnProfile(**p) for p in state["column_profiles"]]
        spec = await intent_agent.parse(state["intent_question"], profiles, state["domain"])
        return {"analysis_spec": spec.model_dump(), "status": "intent_parsed"}

    async def node_analyze(state: PipelineState) -> dict:
        log.info("supervisor_analysis_stub", msg="Analysis requires DB session; executed in worker task.")
        return {"status": "analysis_done"}

    async def node_dashboard(state: PipelineState) -> dict:
        from app.models.schemas import AnalysisSpec
        spec = AnalysisSpec(**state["analysis_spec"])
        dash = await dashboard_agent.generate(spec, state["numeric_results"], state["textual_results"], state["domain"])
        enriched = await insights_agent.enrich(dash, state["domain"])
        return {"dashboard": enriched.model_dump(), "status": "complete"}

    graph.add_node("load_domain", node_load_domain)
    graph.add_node("ingest", node_ingest)
    graph.add_node("await_merge_hitl", node_await_merge_hitl)
    graph.add_node("cleaning_plan", node_cleaning_plan)
    graph.add_node("await_cleaning_hitl", node_await_cleaning_hitl)
    graph.add_node("execute_cleaning", node_execute_cleaning)
    graph.add_node("intent", node_intent)
    graph.add_node("analyze", node_analyze)
    graph.add_node("dashboard", node_dashboard)

    graph.set_entry_point("load_domain")
    graph.add_edge("load_domain", "ingest")
    graph.add_edge("ingest", "await_merge_hitl")
    graph.add_edge("await_merge_hitl", END)

    return graph.compile()
