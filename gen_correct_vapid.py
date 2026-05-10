import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend

# Генерация новой пары ключей (исправлено: SECP256R1)
private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
public_key = private_key.public_key()

# Конвертация в raw base64url (без PEM-обёртки)
def to_base64url_raw(key, is_private=False):
    if is_private:
        # Приватный ключ в raw виде (PKCS#8 без обёртки)
        key_bytes = key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
    else:
        # Публичный ключ в raw виде (uncompressed point)
        key_bytes = key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )
    return base64.urlsafe_b64encode(key_bytes).rstrip(b'=').decode()

public_raw = to_base64url_raw(public_key)
private_raw = to_base64url_raw(private_key, is_private=True)

print("VAPID_PUBLIC_KEY =", public_raw)
print("VAPID_PRIVATE_KEY =", private_raw)