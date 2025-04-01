#!/usr/bin/env python3
"""
generate_keys_rsa.py
Erzeugt ein 2048-Bit RSA-Schlüsselpaar im PEM-Format:
  - my_private_key.pem (unverschlüsselt)
  - my_public_key.pem
mit Warnhinweis, falls vorhandene Dateien überschrieben würden.
"""

import os
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

PRIVATE_KEY_FILENAME = "my_private_key.pem"
PUBLIC_KEY_FILENAME  = "my_public_key.pem"

def main():
    # 0) Warnhinweis, wenn bereits Schlüsseldateien existieren
    files_to_check = [PRIVATE_KEY_FILENAME, PUBLIC_KEY_FILENAME]
    existing_files = [f for f in files_to_check if os.path.exists(f)]
    
    if existing_files:
        print("ACHTUNG: Folgende PEM-Dateien existieren bereits und würden überschrieben werden:")
        for f in existing_files:
            print(f"   - {f}")
        confirm = input("Möchtest du wirklich fortfahren? (ja/Nein) ")
        if confirm.lower() not in ["ja", "yes", "y", "j"]:
            print("Abgebrochen! Es werden keine neuen Schlüssel erzeugt.")
            return

    # 1) Privaten Schlüssel erzeugen (2048 Bit RSA)
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )

    # 2) Öffentlichen Schlüssel ableiten
    public_key = private_key.public_key()

    # 3) Private Key speichern (PEM, unverschlüsselt)
    with open(PRIVATE_KEY_FILENAME, "wb") as f:
        f.write(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            )
        )

    # 4) Public Key speichern (PEM)
    with open(PUBLIC_KEY_FILENAME, "wb") as f:
        f.write(
            public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
        )

    print(f"\nFertig: '{PRIVATE_KEY_FILENAME}' und '{PUBLIC_KEY_FILENAME}' wurden erzeugt.")


if __name__ == "__main__":
    main()
