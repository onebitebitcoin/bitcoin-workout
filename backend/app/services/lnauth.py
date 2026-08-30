from __future__ import annotations

import secrets

import bech32
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed

from app.config import settings


def generate_k1() -> str:
    return secrets.token_hex(32)


def encode_lnurl(k1: str, base_url: str | None = None) -> str:
    """LNURL 을 만든다. base_url 을 주지 않으면 고정 도메인(lnurl_origin)을 쓴다.

    LUD-04 는 이 URL 의 FQDN 으로 지갑의 linkingKey 를 파생하므로, 어떤 도메인을
    넣느냐가 곧 "어느 계정으로 로그인되느냐"다.
    """
    url = f"{base_url or settings.lnurl_origin}/api/v1/auth/lnauth?tag=login&k1={k1}"
    url_bytes = url.encode("utf-8")
    converted = bech32.convertbits(list(url_bytes), 8, 5)
    lnurl = bech32.bech32_encode("lnurl", converted)
    return lnurl.upper()  # LNURL must be uppercase


def verify_signature(k1_hex: str, sig_hex: str, key_hex: str) -> bool:
    """Verify a secp256k1 DER signature where k1 bytes are the pre-hashed digest."""
    try:
        k1_bytes = bytes.fromhex(k1_hex)
        sig_bytes = bytes.fromhex(sig_hex)
        key_bytes = bytes.fromhex(key_hex)

        public_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256K1(), key_bytes)
        # LNAuth: wallet signs k1 directly (k1 is already the 32-byte message digest)
        public_key.verify(sig_bytes, k1_bytes, ec.ECDSA(Prehashed(hashes.SHA256())))
        return True
    except InvalidSignature:
        return False
    except Exception:
        return False
