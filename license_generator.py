#!/usr/bin/env python3
import json
import base64
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# -------------------------------------------------------
# Konfiguration
# -------------------------------------------------------
PRIVATE_KEY_PATH = "my_private_key.pem"  # Dein privater Key (EC oder RSA)
SYM_PASSPHRASE   = "mySuperSymKey_123"   # Wird in der App hartkodiert
SALT             = b"mySalt123"          # Für PBKDF2 (unbedingt gleich in der App)

# -------------------------------------------------------
# Lizendaten, z.B. wie gehabt
# -------------------------------------------------------
license_data = {
    "fingerprint":     "EAE3277B40E7910E",
    "version":         "2.2.0-BE",
    "registered_name": "Bernd Ellera",
    "registered_email":"max@muster.com",
    "expire_date":     "2024-12-31"
}

def main():
    # 1) Privaten Key laden
    with open(PRIVATE_KEY_PATH, "rb") as f:
        private_key = serialization.load_pem_private_key(
            f.read(),
            password=None,  # Falls dein Key passwortgeschützt ist, hier Bytes eingeben
            backend=default_backend()
        )

    # 2) JSON-String erzeugen
    license_json = json.dumps(license_data, ensure_ascii=False)

    # 3) Signatur berechnen (EC-Signatur in diesem Beispiel)
    signature = private_key.sign(
        license_json.encode("utf-8"),
        ec.ECDSA(hashes.SHA256())
    )
    # => raw signature bytes

    # 4) Ein JSON-Objekt draus bauen: { "license": ..., "signature": ... }
    #    So können wir beides zusammen verschlüsseln
    combined_obj = {
        "license":   license_data,
        "signature": base64.b64encode(signature).decode("utf-8")
    }
    combined_json = json.dumps(combined_obj, ensure_ascii=False).encode("utf-8")

    # 5) Symmetrische Verschlüsselung (AES-GCM)
    #    a) PBKDF2, um aus Passphrase -> AES-Schlüssel zu generieren
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,  # 256 bit
        salt=SALT,
        iterations=100_000,
        backend=default_backend()
    )
    aes_key = kdf.derive(SYM_PASSPHRASE.encode("utf-8"))

    #    b) AES-GCM mit zufälligem Nonce (12 Byte)
    nonce = os.urandom(12)
    aesgcm = AESGCM(aes_key)
    ciphertext = aesgcm.encrypt(nonce, combined_json, None)  # "Associated Data" = None

    # 6) Datei-Format: wir speichern { nonce, ciphertext } Base64-codiert
    #    Du kannst es natürlich auch anders strukturieren.
    final_obj = {
        "nonce":     base64.b64encode(nonce).decode("utf-8"),
        "cipher":    base64.b64encode(ciphertext).decode("utf-8")
    }
    final_json = json.dumps(final_obj)

    with open("license.lic", "w", encoding="utf-8") as f:
        f.write(final_json)

    print("License file 'license.lic' erstellt.")

if __name__ == "__main__":
    main()

