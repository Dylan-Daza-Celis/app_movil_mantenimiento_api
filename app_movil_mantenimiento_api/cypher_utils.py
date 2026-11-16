import base64
import secrets
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from django.conf import settings

class CypherUtils:

    @staticmethod
    def encripta(plaintext):
        password = settings.CRYPTO_PASSWORD
        enc_bytes =  CypherUtils.encrypt1(plaintext.encode('utf-8'), password.encode('utf-8'))
        return enc_bytes.decode('utf-8')

    @staticmethod
    def desencripta(cyphertext):
        password = settings.CRYPTO_PASSWORD
        denc_bytes =  CypherUtils.decrypt1(cyphertext.encode('utf-8'), password.encode('utf-8'))
        return denc_bytes.decode('utf-8')

    @staticmethod
    def cipherFernet(password, salt=b'hdjk', iterations=1000):
        # Defaults are retained only for reading legacy ciphertext.
        key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations, backend=default_backend()).derive(password)
        return Fernet(base64.urlsafe_b64encode(key))

    @staticmethod
    def encrypt1(plaintext, password):
        salt = secrets.token_bytes(16)
        encrypted = CypherUtils.cipherFernet(password, salt, 600000).encrypt(plaintext)
        return b'v2:' + base64.urlsafe_b64encode(salt) + b':' + encrypted

    @staticmethod
    def decrypt1(ciphertext, password):
        if ciphertext.startswith(b'v2:'):
            try:
                _, encoded_salt, encrypted = ciphertext.split(b':', 2)
                salt = base64.b64decode(encoded_salt, altchars=b'-_', validate=True)
                if len(salt) != 16:
                    raise ValueError('Invalid salt')
            except (ValueError, TypeError) as exc:
                raise InvalidToken() from exc
            return CypherUtils.cipherFernet(password, salt, 600000).decrypt(encrypted)
        return CypherUtils.cipherFernet(password).decrypt(ciphertext)
