from enum import Enum
from dataclasses import dataclass
import logging
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.merchant.models import MerchantOrder

logger = logging.getLogger(__name__)

class ActionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    CONFLICT = "CONFLICT"
    ERROR = "ERROR"

@dataclass
class ActionResult:
    status: ActionStatus
    message: str

async def execute_repair_action(
    session: AsyncSession,
    merchant_order_id_pk: str,  # The UUID primary key of the MerchantOrder
    expected_precondition_status: str = "UNPAID",
    target_status: str = "PAID"
) -> ActionResult:
    """
    Executes a transactionally safe, atomic conditional mutation.
    Updates the merchant order to PAID only if it is still UNPAID.
    """
    try:
        stmt = (
            update(MerchantOrder)
            .where(
                MerchantOrder.id == merchant_order_id_pk,
                MerchantOrder.status == expected_precondition_status
            )
            .values(status=target_status)
        )
        
        result = await session.execute(stmt)
        
        if result.rowcount == 1:
            await session.commit()
            return ActionResult(ActionStatus.SUCCESS, "Atomic update succeeded.")
        elif result.rowcount == 0:
            # 0 rows affected means the precondition failed concurrently.
            await session.rollback()
            return ActionResult(
                ActionStatus.CONFLICT, 
                f"Atomic update failed. MerchantOrder {merchant_order_id_pk} was not in '{expected_precondition_status}' state."
            )
        else:
            # Should never happen on a primary key update
            await session.rollback()
            return ActionResult(ActionStatus.ERROR, f"Unexpected rowcount: {result.rowcount}")

    except Exception as e:
        logger.exception(f"Error executing repair action on order {merchant_order_id_pk}")
        await session.rollback()
        return ActionResult(ActionStatus.ERROR, str(e))
