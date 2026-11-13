from fastapi import FastAPI
from api.router import router as expense_router
from services.saga.payout_service import department_budgets, budget_deducted_ledger, bank_transfer_ledger

app = FastAPI(
    title="Enterprise Expense & Audit System API",
    description="企业级智能差旅报销与费用合规审计中台 (LangGraph + HITL + Saga)",
    version="1.0.0",
)

app.include_router(expense_router)


@app.get("/api/v1/budgets", tags=["Financial Ledger"], summary="查询企业各部门实时预算池与幂等账本")
def get_department_budgets() -> dict:
    return {
        "department_budgets": department_budgets,
        "budget_deducted_invoices": list(budget_deducted_ledger),
        "bank_transfer_receipts": bank_transfer_ledger,
    }