import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

# Загружаем сгенерированные ключи
with open('private_key.pem', 'rb') as f:
    private_pem = f.read()
private_key = serialization.load_pem_private_key(
    private_pem,
    password=None,
    backend=default_backend()
)

with open('public_key.pem', 'rb') as f:
    public_pem = f.read()
public_key = serialization.load_pem_public_key(
    public_pem,
    backend=default_backend()
)

# Преобразуем в base64url
def to_base64url(key, is_private=False):
    if not is_private:
        # Публичный ключ в формате uncompressed point
        key_bytes = key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )
    else:
        # Приватный ключ в PKCS#8 без шифрования
        key_bytes = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
    return base64.urlsafe_b64encode(key_bytes).rstrip(b'=').decode()

print("VAPID_PUBLIC_KEY =", to_base64url(public_key))
print("VAPID_PRIVATE_KEY =", to_base64url(private_key, is_private=True))