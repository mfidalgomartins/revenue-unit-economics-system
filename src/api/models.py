"""Typed public response contracts for aggregate dashboard data."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(StrictModel):
    status: str


class KpiCard(StrictModel):
    label: str
    value: str
    delta: float | None
    deltaText: str
    tone: str


class MonthlyPoint(StrictModel):
    month: str
    revenue: float
    cost: float
    margin: float
    activeCustomers: int


class CohortPoint(StrictModel):
    monthsSince: int
    revenueRetention: float


class UnitEconomicsPoint(StrictModel):
    channel: str
    customersAcquired: int
    totalSpend: float
    CAC: float
    avgLTV: float
    ltvToCac: float
    paybackCAC: float | None
    payback: float | None
    paybackStatus: str
    paybackHorizon: int
    status: str


class SegmentPoint(StrictModel):
    segment: str
    revenue: float
    cost: float
    margin: float
    marginPct: float
    customers: int


class AverageRevenuePoint(StrictModel):
    segment: str
    avgRevTx: float
    customers: int


class HistogramBin(StrictModel):
    bucketStart: float
    bucketEnd: float
    count: int


class RegionPoint(StrictModel):
    region: str
    revenue: float
    cost: float
    margin: float
    marginPct: float
    customers: int


class RiskPoint(StrictModel):
    entity: str
    metricValues: str
    riskInterpretation: str
    recommendedAction: str
    priorityScore: float
    priorityBand: str


class DecisionCommand(StrictModel):
    decision: str
    decisionText: str
    scale: str
    scaleText: str
    intervene: str
    interveneText: str
    impact: str
    impactText: str


class SummaryInsight(StrictModel):
    title: str
    badge: str
    tone: str
    text: str


class DashboardSnapshot(StrictModel):
    kpis: list[KpiCard]
    monthly: list[MonthlyPoint]
    cohort: list[CohortPoint]
    unitEconomics: list[UnitEconomicsPoint]
    segments: list[SegmentPoint]
    averageRevenue: list[AverageRevenuePoint]
    histogramBins: list[HistogramBin]
    regions: list[RegionPoint]
    risks: list[RiskPoint]
    decision: DecisionCommand
    insights: list[SummaryInsight]
    chartInsights: dict[str, str]
    summaryContext: str
    privacy: dict[str, int | str]
    analyticalScope: dict[str, str]
