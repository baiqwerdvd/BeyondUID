import base64
from typing import Any
from urllib.parse import urlparse, urlunparse

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

AES_BLOCK_SIZE = 16


def pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        return data
    padding_len = data[-1]
    if padding_len > 0 and padding_len <= AES_BLOCK_SIZE:
        if all(b == padding_len for b in data[-padding_len:]):
            return data[:-padding_len]
    return data


def aes_decrypt(cipher: bytes, key: bytes, iv: bytes) -> bytes:
    cipher_obj = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher_obj.decryptor()
    decrypted = decryptor.update(cipher) + decryptor.finalize()
    return decrypted


class RemoteConfigUtils:
    @staticmethod
    def _config_key(is_oversea: bool = False) -> bytes:
        if is_oversea:
            return base64.b64decode(b"cZm86UfDp/kgJ3agKx+HZA==")
        else:
            return base64.b64decode(b"Wgxugl5qVirx7r3km6nXtA==")

    @staticmethod
    def get_text(ciphertext_b64: str, is_oversea: bool = False) -> str:
        text_bytes = base64.b64decode(ciphertext_b64)
        key = RemoteConfigUtils._config_key(is_oversea=is_oversea)
        decrypted_bytes = aes_decrypt(text_bytes[16:], key, text_bytes[:16])
        decrypted_bytes = pkcs7_unpad(decrypted_bytes)
        return decrypted_bytes.decode("utf-8")


class U8ConfigUtils:
    @staticmethod
    def decrypt_bin(cipher: bytes) -> bytes:
        AES_KEY = bytes.fromhex(
            "C0F30E1CE763BBC21CC355A34303AC50399444BFF68C4A22AF398C0A166EE143"
        )
        AES_IV = bytes.fromhex("33467861192750649501937264608400")
        decrypted_bytes = aes_decrypt(cipher, AES_KEY, AES_IV)
        return pkcs7_unpad(decrypted_bytes)


def strip_url_query_params(url: str) -> str:
    if not url or not isinstance(url, str):
        return url
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def normalize_data_for_comparison(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: normalize_data_for_comparison(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [normalize_data_for_comparison(item) for item in data]
    elif isinstance(data, str) and data.startswith(("http://", "https://")):
        return strip_url_query_params(data)
    return data
