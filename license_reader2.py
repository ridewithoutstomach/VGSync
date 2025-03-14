#!/usr/bin/env python3

import json
import base64
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

# Die gleichen Werte wie in license_generator_rsa.py und license_check.py
SYM_PASSPHRASE = "kLm1(bksmelIkmeM;p$-kslpw28612535"
SALT = b"meloennsLWNF"

def main():
    # 1) license.lic laden
    filename = "license.lic"
    if not os.path.isfile(filename):
        print(f"[ERROR] '{filename}' nicht gefunden!")
        return

    with open(filename, "r", encoding="utf-8") as f:
        data = json.load(f)  # => {"nonce": "...", "cipher": "..."}

    nonce_b  = base64.b64decode(data["nonce"])
    cipher_b = base64.b64decode(data["cipher"])

    # 2) PBKDF2 => AES-Key
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

    # => Das Plaintext ist ein JSON mit { "license": {...}, "signature": "..." }
    combined_obj = json.loads(plaintext.decode("utf-8", errors="replace"))

    # 4) Zeigen, was drinsteht
    #    Du hast jetzt z. B. combined_obj["license"] und combined_obj["signature"]
    license_data  = combined_obj.get("license", {})
    signature_b64 = combined_obj.get("signature", "")

    print("========== DECRYPTED license.lic ==========")
    print("LICENSE-DATA:\n", json.dumps(license_data, indent=2, ensure_ascii=False))
    print("\nSIGNATURE (Base64):\n", signature_b64)
    print("===========================================\n")

if __name__ == "__main__":
    main()
