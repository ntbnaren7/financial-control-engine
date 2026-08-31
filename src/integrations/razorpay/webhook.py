import hmac
import hashlib

def verify_signature(payload_body: bytes, signature: str, secret: str) -> bool:
    """
    Verifies the Razorpay webhook signature.
    
    The signature is an HMAC hex digest of the raw webhook body using the
    webhook secret as the key.
    """
    if not signature or not secret:
        return False

    # Compute HMAC SHA256 of the raw body
    expected_signature = hmac.new(
        key=secret.encode('utf-8'),
        msg=payload_body,
        digestmod=hashlib.sha256
    ).hexdigest()

    # Use hmac.compare_digest to prevent timing attacks
    return hmac.compare_digest(expected_signature, signature)
