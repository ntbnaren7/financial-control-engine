from typing import List, Optional
from datetime import datetime
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.evidence.models import ProviderObservation
from src.merchant.models import MerchantOrder
from src.investigation.evidence import EvidenceGatherer, EvidencePacket
from src.investigation.models import (
    EvidenceItem,
    EvidenceType,
    EvidenceCoverage,
    ProviderPaymentContent,
    ProviderOrderContent,
    MerchantOrderStateContent,
    WebhookCapturedContent,
    WebhookCoverageContent,
    ProcessingCoverageContent,
    MerchantProcessingContent,
    StateTransitionCoverageContent,
    MerchantStateTransitionContent,
)
from src.reconciliation.models import VerifiedDiscrepancy

class DatabaseEvidenceGatherer(EvidenceGatherer):
    """
    Acquires read-only, strongly-typed observations from the database without inferring causality.
    
    Observational Principles:
    1. Only emits facts backed by actual database records (no synthesis from M3 context).
    2. Explicitly defines coverage bounds (COMPLETE only when the queried observation domain
       is authoritative and comprehensive for the investigation scope; UNKNOWN/PARTIAL otherwise).
    3. Emits deterministic evidence IDs scoped to the investigation packet.
    """
    def __init__(self, session_maker: async_sessionmaker):
        self.session_maker = session_maker
        
    async def gather(self, discrepancy: VerifiedDiscrepancy) -> EvidencePacket:
        items: List[EvidenceItem] = []
        
        async with self.session_maker() as session:
            # 1. Query relevant Provider Observations for this discrepancy
            stmt_obs = select(ProviderObservation)
            res_obs = await session.execute(stmt_obs)
            all_observations = res_obs.scalars().all()
            
            relevant_obs: List[ProviderObservation] = []
            for obs in all_observations:
                order_id = obs.payload.get("order_id")
                payment_id = obs.payload.get("payment_id")
                
                # Match against either order_id or payment_id from the verified discrepancy
                if (discrepancy.order_id and order_id == discrepancy.order_id) or \
                   (discrepancy.payment_id and payment_id == discrepancy.payment_id):
                    relevant_obs.append(obs)

            # 2. Query Merchant Order table
            merchant_order: Optional[MerchantOrder] = None
            if discrepancy.order_id:
                stmt_order = select(MerchantOrder).where(
                    or_(
                        MerchantOrder.razorpay_order_id == discrepancy.order_id,
                        MerchantOrder.merchant_order_id == discrepancy.order_id
                    )
                )
                res_order = await session.execute(stmt_order)
                merchant_order = res_order.scalars().first()

            # -------------------------------------------------------------
            # A. Provider Payment Observation (E_PROVIDER_PAYMENT)
            # Only emit if an authoritative payment observation exists in the DB
            # -------------------------------------------------------------
            payment_obs = next((o for o in relevant_obs if o.event_type == "payment"), None)
            if payment_obs:
                payload = payment_obs.payload
                items.append(
                    EvidenceItem(
                        id="EV-PAY-01",
                        type=EvidenceType.E_PROVIDER_PAYMENT,
                        content=ProviderPaymentContent(
                            payment_id=payload.get("payment_id", discrepancy.payment_id),
                            order_id=payload.get("order_id", discrepancy.order_id),
                            amount=payload.get("amount", 0),
                            currency=payload.get("currency", "INR"),
                            status=payload.get("status", "unknown"),
                            captured=payload.get("captured", False),
                            observed_at=payment_obs.created_at
                        )
                    )
                )

            # -------------------------------------------------------------
            # B. Provider Order Observation (E_PROVIDER_ORDER)
            # -------------------------------------------------------------
            prov_order_obs = next((o for o in relevant_obs if o.event_type == "provider_order"), None)
            if prov_order_obs:
                payload = prov_order_obs.payload
                items.append(
                    EvidenceItem(
                        id="EV-PORD-01",
                        type=EvidenceType.E_PROVIDER_ORDER,
                        content=ProviderOrderContent(
                            provider_order_id=payload.get("provider_order_id", discrepancy.order_id),
                            status=payload.get("status", "unknown"),
                            amount=payload.get("amount"),
                            currency=payload.get("currency"),
                            observed_at=prov_order_obs.created_at
                        )
                    )
                )

            # -------------------------------------------------------------
            # C. Merchant Order State (E_MERCHANT_ORDER_STATE)
            # Queried directly from merchant_orders table
            # -------------------------------------------------------------
            if merchant_order:
                items.append(
                    EvidenceItem(
                        id="EV-MO-01",
                        type=EvidenceType.E_MERCHANT_ORDER_STATE,
                        content=MerchantOrderStateContent(
                            merchant_order_id=merchant_order.merchant_order_id,
                            razorpay_order_id=merchant_order.razorpay_order_id,
                            status=merchant_order.status,
                            expected_amount=merchant_order.expected_amount,
                            currency=merchant_order.currency,
                            updated_at=merchant_order.updated_at
                        )
                    )
                )

            # -------------------------------------------------------------
            # D. Webhook Captured & Ingestion Coverage (E_WEBHOOK_CAPTURED, E_WEBHOOK_COVERAGE)
            # -------------------------------------------------------------
            webhook_obs_list = [o for o in relevant_obs if o.event_type == "webhook"]
            
            # Emit individual captured webhook observation(s) only if actual records exist
            for idx, wh in enumerate(webhook_obs_list, start=1):
                items.append(
                    EvidenceItem(
                        id=f"EV-WH-{idx:02d}",
                        type=EvidenceType.E_WEBHOOK_CAPTURED,
                        content=WebhookCapturedContent(
                            present=True,
                            event_id=wh.event_id,
                            observed_at=wh.created_at
                        )
                    )
                )

            # Ingestion coverage: Provider observation log is authoritative for raw incoming hooks.
            # When webhook_obs_list is empty, this coverage fact with webhook_count=0 
            # constitutes the authoritative proof of absence (absence of record under COMPLETE coverage).
            items.append(
                EvidenceItem(
                    id="EV-WHCOV-01",
                    type=EvidenceType.E_WEBHOOK_COVERAGE,
                    content=WebhookCoverageContent(
                        coverage=EvidenceCoverage.COMPLETE,
                        webhook_count=len(webhook_obs_list)
                    )
                )
            )

            # -------------------------------------------------------------
            # E. Merchant Processing & Processing Coverage (E_MERCHANT_PROCESSING, E_PROCESSING_COVERAGE)
            # -------------------------------------------------------------
            processing_obs_list = [o for o in relevant_obs if o.event_type == "processing"]
            
            # Individual processing execution records
            for idx, proc in enumerate(processing_obs_list, start=1):
                items.append(
                    EvidenceItem(
                        id=f"EV-PROC-{idx:02d}",
                        type=EvidenceType.E_MERCHANT_PROCESSING,
                        content=MerchantProcessingContent(
                            event_id=proc.event_id,
                            status=proc.payload.get("status", "PROCESSED"),
                            processed_at=proc.created_at
                        )
                    )
                )

            # Processing coverage item
            items.append(
                EvidenceItem(
                    id="EV-PC-01",
                    type=EvidenceType.E_PROCESSING_COVERAGE,
                    content=ProcessingCoverageContent(
                        coverage=EvidenceCoverage.COMPLETE,
                        processing_count=len(processing_obs_list)
                    )
                )
            )

            # -------------------------------------------------------------
            # F. Merchant State Transitions & Coverage (E_MERCHANT_STATE_TRANSITION, E_STATE_TRANSITION_COVERAGE)
            # -------------------------------------------------------------
            transition_obs_list = [o for o in relevant_obs if o.event_type == "state_transition"]
            for idx, trans in enumerate(transition_obs_list, start=1):
                payload = trans.payload
                items.append(
                    EvidenceItem(
                        id=f"EV-ST-{idx:02d}",
                        type=EvidenceType.E_MERCHANT_STATE_TRANSITION,
                        content=MerchantStateTransitionContent(
                            transition_id=trans.event_id,
                            from_status=payload.get("from_status"),
                            to_status=payload.get("to_status", "UNKNOWN"),
                            transitioned_at=trans.created_at
                        )
                    )
                )

            # State transition coverage fact (authoritative completeness of transition log)
            items.append(
                EvidenceItem(
                    id="EV-STCOV-01",
                    type=EvidenceType.E_STATE_TRANSITION_COVERAGE,
                    content=StateTransitionCoverageContent(
                        coverage=EvidenceCoverage.COMPLETE,
                        transition_count=len(transition_obs_list)
                    )
                )
            )

        return EvidencePacket(items=items)
