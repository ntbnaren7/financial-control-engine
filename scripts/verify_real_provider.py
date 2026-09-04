"""
verify_real_provider.py
=======================
Read-only smoke test for RealRazorpayProvider against Razorpay Test Mode.

Purpose:
    Proves that FCE can authenticate to the Razorpay API and retrieve +
    normalize a real Test Mode payment — before any write/mutation is attempted.

What this tests:
    - RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are valid Test Mode credentials
    - RealRazorpayProvider.get_payment() reaches the API and returns a response
    - RazorpayV2Normalizer.normalize_payment() produces a canonical observation
    - No FCE state machine, no DB, no mutation — purely the read boundary

Usage:
    RAZORPAY_KEY_ID=rzp_test_... RAZORPAY_KEY_SECRET=... PAYMENT_ID=pay_... \\
        uv run python scripts/verify_real_provider.py

    Or with a .env file already populated:
        uv run python scripts/verify_real_provider.py --payment-id pay_...

The PAYMENT_ID must be a real Test Mode payment that exists in your Razorpay
Test dashboard. Create one there if you don't have one yet.
"""

import asyncio
import argparse
import os
import sys

# Pre-load .env so credentials are visible to FCESettings.load() regardless of
# whether the shell has already exported them (e.g. when running via uv without
# a full process tree that inherits the uvicorn environment).
from dotenv import load_dotenv
load_dotenv(".env")

from src.config.settings import FCESettings
from src.integrations.razorpay.real_provider import RealRazorpayProvider
from src.integrations.razorpay.normalizer import RazorpayV2Normalizer
from src.integrations.razorpay.client import ProviderClientError, ProviderNetworkError


def _check_credentials(settings) -> bool:
    key_id = settings.razorpay.key_id
    key_secret = settings.razorpay.key_secret.get_secret_value()
    if not key_id or not key_secret:
        print("[FAIL] RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be set.")
        print("       Export them or add them to .env before running this script.")
        return False
    if not key_id.startswith("rzp_test_"):
        print(f"[WARN] key_id '{key_id}' does not look like a Test Mode key (expected 'rzp_test_...').")
        print("       Proceeding, but mutations will be against your live account if you run them.")
    return True


async def run(payment_id: str) -> int:
    """
    Returns 0 on success, 1 on failure.
    """
    settings = FCESettings.load()

    if not _check_credentials(settings):
        return 1

    provider = RealRazorpayProvider(settings=settings.razorpay)
    normalizer = RazorpayV2Normalizer()

    print(f"\n[1/3] Fetching payment '{payment_id}' from Razorpay Test Mode...")
    try:
        payment = await provider.get_payment(payment_id)
    except ProviderClientError as e:
        print(f"[FAIL] Provider rejected the request (4xx): {e}")
        print("       Likely cause: payment does not exist in Test Mode, or credentials are wrong.")
        await provider.close()
        return 1
    except ProviderNetworkError as e:
        print(f"[FAIL] Network error reaching Razorpay: {e}")
        await provider.close()
        return 1

    print(f"[OK]   Raw payment from API:")
    print(f"         id            = {payment.id}")
    print(f"         status        = {payment.status}")
    print(f"         amount        = {payment.amount} paisa ({payment.amount / 100:.2f} {payment.currency})")
    print(f"         order_id      = {payment.order_id}")
    print(f"         captured      = {payment.captured}")
    print(f"         method        = {payment.method}")
    if payment.error_code:
        print(f"         error_code    = {payment.error_code}")
        print(f"         error_desc    = {payment.error_description}")

    print(f"\n[2/3] Normalizing payment to canonical FCE observation...")
    # normalizer.normalize_payment expects (raw_payload: dict, evidence_id: str)
    observation = normalizer.normalize_payment(payment.model_dump(), evidence_id="probe_read_only")
    print(f"[OK]   Canonical observation:")
    print(f"         observation_id      = {observation.observation_id}")
    print(f"         provider            = {observation.provider}")
    print(f"         provider_reference  = {observation.provider_reference}")
    print(f"         canonical_status    = {observation.canonical_status.value}")
    print(f"         observed_amount     = {observation.observed_amount}")
    print(f"         correlation_keys    = provider={observation.correlation_keys.provider}, "
          f"provider_ref={observation.correlation_keys.provider_ref}, "
          f"internal_ref={observation.correlation_keys.internal_ref}")

    print(f"\n[3/3] Verifying order fetch (read boundary validation)...")
    if payment.order_id:
        try:
            order = await provider.get_order(payment.order_id)
            print(f"[OK]   Order '{order.id}' fetched — status={order.status}, "
                  f"amount_paid={order.amount_paid}, amount_due={order.amount_due}")
        except ProviderClientError as e:
            print(f"[WARN] get_order returned 4xx: {e} — this is non-fatal for read verification.")
    else:
        print("[SKIP] Payment has no order_id — skipping order fetch.")

    await provider.close()

    print(f"\n{'='*60}")
    print(f"  READ BOUNDARY VERIFIED")
    print(f"  RealRazorpayProvider can reach Razorpay Test Mode.")
    print(f"  canonical_status={observation.canonical_status.value}")
    print(f"{'='*60}\n")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Read-only smoke test: verify FCE can fetch a real Razorpay Test Mode payment."
    )
    parser.add_argument(
        "--payment-id",
        default=os.environ.get("PAYMENT_ID", ""),
        help="Razorpay Test Mode payment ID (pay_...). Also readable from PAYMENT_ID env var.",
    )
    args = parser.parse_args()

    if not args.payment_id:
        parser.error(
            "Provide a payment ID via --payment-id or PAYMENT_ID env var.\n"
            "Create one in your Razorpay Test Mode dashboard if you don't have one."
        )

    exit_code = asyncio.run(run(args.payment_id))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
