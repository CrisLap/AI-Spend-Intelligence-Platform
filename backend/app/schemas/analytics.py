from __future__ import annotations

from pydantic import BaseModel


class SpendByCategory(BaseModel):
    category: str
    total: float
    count: int
    percentage: float


class SpendByMonth(BaseModel):
    month: str
    total: float
    count: int


class TopSupplier(BaseModel):
    supplier: str
    total: float
    count: int


class DashboardData(BaseModel):
    total_spend: float
    total_items: int
    total_documents: int
    anomaly_count: int
    duplicate_count: int
    spend_by_category: list[SpendByCategory]
    spend_by_month: list[SpendByMonth]
    top_suppliers: list[TopSupplier]
    top_categories: list[SpendByCategory]
