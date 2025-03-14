import json
import base64

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

# --------------------------------------------------------------------------------
# Dein öffentlicher RSA-Key (PEM) als Byte-String:
# --------------------------------------------------------------------------------
PUBLIC_KEY_PEM = b"""\
-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAsqnbaTea/9uO/Xo3i153
TmQWz1IMzZ/vuAz6BaCcCQrfvIInSxsu1Ofc80tEkajlDZE7HSRE6+bnTOI44fLm
9igIZbRAiSq8Tw5oISRjwKRbrCVLEvJbl6+Dh3dHJ4y7Yhn/OhCnF7/LAWduymAK
FF+Sqyf7SOS1YfjnNp0pjgsOpeWIGf2hpM3lHS1Jprnj8LJQaVPr09u+y2sX8K8t
81ST4DE3qpQm4SrCt/WDZ4sKTzGasPcDgnZJjbvKJ6KTWmQ3zG0A7/PmIQ9+ZbaP
23qQ7plykw2vdAdR5A9ApuASvX/9xHXxB8QpMODToCx9QsjnJAaWLi5aamfLvDPX
IQIDAQAB
-----END PUBLIC KEY-----
"""

SYM_PASSPHRASE = "kLm1(bksmelIkmeM;p$-kslpw28612535"
SALT           = b"meloennsLWNF"

def load_license(license_file_path: str):
    """
    Liest 'license.lic', entschlüsselt sie (AES-GCM) und prüft die RSA-Signatur (PSS).
    Gibt ein Dictionary mit den Feldern "fingerprint", "version", "registered_name", ...
    """
    # 1) Datei laden (JSON)
    with open(license_file_path, "r", encoding="utf-8") as f:
        content = json.load(f)  # => { "nonce": "...", "cipher": "..." }

    nonce_b  = base64.b64decode(content["nonce"])
    cipher_b = base64.b64decode(content["cipher"])

    # 2) AES-Key aus Passphrase (PBKDF2)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SALT,
        iterations=100_000,
        backend=default_backend()
    )
    aes_key = kdf.derive(SYM_PASSPHRASE.encode("utf-8"))

    # 3) AES-GCM decrypt
    aesgcm = AESGCM(aes_key)
    plaintext = aesgcm.decrypt(nonce_b, cipher_b, None)

    # => { "license": {...}, "signature": "..." }
    combined_obj = json.loads(plaintext)

    # 4) Felder extrahieren
    license_data = combined_obj["license"]
    sig_b64      = combined_obj["signature"]
    signature    = base64.b64decode(sig_b64)

    # 5) Public Key laden
    public_key = serialization.load_pem_public_key(
        PUBLIC_KEY_PEM,
        backend=default_backend()
    )

    # 6) Original-Klartext war der JSON-String von "license_data"
    lic_json_str = json.dumps(license_data, ensure_ascii=False)

    # 7) Signatur prüfen (RSA-PSS, SHA256)
    try:
        public_key.verify(
            signature,
            lic_json_str.encode("utf-8"),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
    except Exception as e:
        raise ValueError(f"Signature invalid! {e}")

    # => Alles OK
    return license_data
