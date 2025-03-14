#!/usr/bin/env python3
"""
license_generator_rsa.py
Interaktives Skript, um eine lizenz.lic-Datei zu erstellen:
 - Die eingegebenen Felder werden als JSON gespeichert,
 - Dann mit RSA-Signatur (PSS) signiert,
 - Dann symmetrisch (AES-GCM) verschlüsselt,
 - Abschließend in license.lic abgelegt.
 - Zusätzlich wird eine Versioninfo-Zeile ausgegeben.
"""

import json
import base64
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# -----------------------------------------------------------------------
# Konfiguration: RSA-Privater Key (PEM) + SymPass + SALT
# -----------------------------------------------------------------------
PRIVATE_KEY_PATH = "my_private_key.pem"      # Pfad zum RSA-Privatkey (PEM)
SYM_PASSPHRASE = "kLm1(bksmelIkmeM;p$-kslpw28612535"
SALT           = b"meloennsLWNF"

def main():
    print("****************************************************")
    print("* Interaktiver License Generator (AES + RSA-PSS)   *")
    print("****************************************************\n")

    # 1) Lizenzdaten interaktiv abfragen
    fingerprint      = input("Fingerprint (z.B. EAE3277B40E7910E): ")
    version          = input("Version (z.B. 2.2.0-BE): ")
    registered_name  = input("Registered Name (z.B. Bernd Eller): ")
    registered_email = input("Registered E-Mail (z.B. max@muster.com): ")
    expire_date      = input("Expire-Date (YYYY-MM-DD, z.B. 2025-12-31): ")

    license_data = {
        "fingerprint":      fingerprint.strip(),
        "version":          version.strip(),
        "registered_name":  registered_name.strip(),
        "registered_email": registered_email.strip(),
        "expire_date":      expire_date.strip()
    }

    # 2) Privaten Key laden
    try:
        with open(PRIVATE_KEY_PATH, "rb") as f:
            private_key = serialization.load_pem_private_key(
                f.read(),
                password=None,  # Falls dein Key passwortgeschützt ist, hier Bytes eingeben
                backend=default_backend()
            )
    except Exception as e:
        print(f"[ERROR] Konnte Private Key '{PRIVATE_KEY_PATH}' nicht laden:", e)
        return

    # 3) JSON-String
    license_json = json.dumps(license_data, ensure_ascii=False)
    
    # 4) RSA-Signatur (PSS + SHA256)
    try:
        signature = private_key.sign(
            license_json.encode("utf-8"),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
    except Exception as e:
        print("[ERROR] Fehler beim Signieren:", e)
        return

    # 5) Gemeinsames JSON-Objekt (Lizenz + Signatur)
    combined_obj = {
        "license":   license_data,
        "signature": base64.b64encode(signature).decode("utf-8")
    }
    combined_json_bytes = json.dumps(combined_obj, ensure_ascii=False).encode("utf-8")

    # 6) Symmetrische Verschlüsselung (AES-GCM)
    #    a) Key aus Passphrase via PBKDF2
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,           # 256 bit
        salt=SALT,
        iterations=100_000,
        backend=default_backend()
    )
    aes_key = kdf.derive(SYM_PASSPHRASE.encode("utf-8"))

    #    b) Nonce + AESGCM
    nonce = os.urandom(12)
    aesgcm = AESGCM(aes_key)
    ciphertext = aesgcm.encrypt(nonce, combined_json_bytes, None)

    # 7) In JSON verpacken + Base64 => "license.lic"
    final_obj = {
        "nonce":  base64.b64encode(nonce).decode("utf-8"),
        "cipher": base64.b64encode(ciphertext).decode("utf-8")
    }
    final_json_str = json.dumps(final_obj)

    output_filename = "license.lic"
    try:
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(final_json_str)
        print(f"\nFertig: '{output_filename}' wurde erstellt!")
    except Exception as e:
        print("[ERROR] Konnte Datei nicht schreiben:", e)
        return

    # 8) Zeile für serverseitige versioninfo.txt
    server_line = f"{license_data['version']} ; ENABLE ; {license_data['expire_date']}"
    print("\nBitte füge folgende Zeile in deine 'versioninfo.txt' ein und lade sie hoch:")
    print(f"   {server_line}")

if __name__ == "__main__":
    main()
