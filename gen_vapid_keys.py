# gen_vapid_keys.py
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend
import base64

# Генерация ключей
private_key = ec.generate_private_key(ec.SECP256r1(), default_backend())
public_key = private_key.public_key()

# Конвертация в base64url
def to_base64url(key, is_private=False):
    if is_private:
        key_bytes = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
    else:
        key_bytes = key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )
    return base64.urlsafe_b64encode(key_bytes).rstrip(b'=').decode()

print("VAPID_PUBLIC_KEY =", to_base64url(public_key))
print("VAPID_PRIVATE_KEY =", to_base64url(private_key, is_private=True))