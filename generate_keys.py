#!/usr/bin/env python3
"""
generate_keys_rsa.py
Erzeugt ein 2048-Bit RSA-Schlüsselpaar im PEM-Format:
  - my_private_key.pem (unverschlüsselt)
  - my_public_key.pem
"""

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

def main():
    # 1) Privaten Schlüssel erzeugen (2048 Bit RSA)
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )

    # 2) Öffentlichen Schlüssel ableiten
    public_key = private_key.public_key()

    # 3) Private Key speichern (PEM, unverschlüsselt)
    with open("my_private_key.pem", "wb") as f:
        f.write(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            )
        )

    # 4) Public Key speichern (PEM)
    with open("my_public_key.pem", "wb") as f:
        f.write(
            public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
        )

    print("Fertig: my_private_key.pem und my_public_key.pem erzeugt.")

if __name__ == "__main__":
    main()
