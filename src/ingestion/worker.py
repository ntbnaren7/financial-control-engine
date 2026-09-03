import structlog
from typing import Callable, Dict, List, Optional
from datetime import datetime, timezone

from src.domain.ingestion.models import IngestionPayload
from src.engine.adapters.base_adapter import DomainAdapter
from src.engine.adapters.razorpay_payment_adapter import RazorpayPaymentAdapter
from src.storage.substrate_repo import ObservationRepository, EvidenceRepository

logger = structlog.get_logger()


class IngestionWorker:
    """
    Decoupled ingestion worker that claims durable payloads from the ingress substrate,
    normalizes them through the provider DomainAdapter, and persists canonical Observation
    and Evidence records before triggering downstream reconciliation.
    """

    def __init__(
        self,
        worker_id: str,
        ingestion_repo,
        observation_repo: ObservationRepository,
        evidence_repo: EvidenceRepository,
        on_observation_persisted: Optional[Callable[[any], None]] = None,
    ):
        self.worker_id = worker_id
        self.ingestion_repo = ingestion_repo
        self.observation_repo = observation_repo
        self.evidence_repo = evidence_repo
        self.on_observation_persisted = on_observation_persisted
        self._adapters: Dict[str, DomainAdapter] = {
            "razorpay": RazorpayPaymentAdapter(),
        }

    def register_adapter(self, provider: str, adapter: DomainAdapter) -> None:
        self._adapters[provider.lower()] = adapter

    def process_batch(self, limit: int = 10, lease_seconds: int = 30) -> int:
        payloads = self.ingestion_repo.claim_pending_payloads(
            worker_id=self.worker_id,
            limit=limit,
            lease_seconds=lease_seconds,
        )

        processed_count = 0
        for payload in payloads:
            try:
                adapter = self._adapters.get(payload.provider.lower())
                if not adapter:
                    raise ValueError(f"No DomainAdapter registered for provider '{payload.provider}'")

                obs, ev = adapter.normalize_payload(payload.raw_payload)

                # Persist immutable evidence first
                self.evidence_repo.save(ev)
                # Persist canonical observation
                self.observation_repo.save(obs)

                # Optional callback / event trigger for incremental reconciliation
                if self.on_observation_persisted:
                    self.on_observation_persisted(obs)

                self.ingestion_repo.mark_processed(payload.payload_id)
                processed_count += 1
                logger.info(
                    "IngestionWorker: Processed payload successfully",
                    payload_id=payload.payload_id,
                    provider=payload.provider,
                    obs_id=obs.observation_id,
                )
            except Exception as e:
                logger.error(
                    "IngestionWorker: Failed to process payload",
                    payload_id=payload.payload_id,
                    error=str(e),
                )
                self.ingestion_repo.mark_processed(payload.payload_id, error=str(e))

        return processed_count
