# 🌟 全局共享夹具：重置部门预算/幂等账本、提供标准测试发票数据工厂
import sys
from pathlib import Path
import pytest

# 确保项目根目录在 sys.path 中，任何目录下执行 pytest 都能正常导入 schemas / services / api
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.saga.payout_service import (
    department_budgets,
    budget_deducted_ledger,
    bank_transfer_ledger,
)


@pytest.fixture(autouse=True)
def reset_financial_ledgers():
    """
    全局自动隔离夹具 (autouse=True)：
    在每个测试用例运行前，强制重置部门预算池与幂等账本，杜绝测试用例间的脏数据污染。
    """
    department_budgets.clear()
    department_budgets.update({
        "TECH_DEPT": 50000.00,
        "SALES_DEPT": 30000.00,
    })
    budget_deducted_ledger.clear()
    bank_transfer_ledger.clear()
    yield