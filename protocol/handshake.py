"""连接建立时的双向身份认证。

两端各自生成随机挑战并同时发出，再各自用共享密钥对收到的挑战做 HMAC-SHA256 应答。
一个往返即完成相互认证，两端代码完全对称，无需区分主动方与被动方。

共享密钥由父进程生成，经**环境变量**传给子进程。不得经命令行参数传递：
``/proc/<pid>/cmdline`` 对本机所有用户可读，而 ``/proc/<pid>/environ`` 仅属主可读。
"""
import asyncio
import hashlib
import hmac
import os

from .framing import ProtocolError, encode_raw, read_raw

#: 挑战随机数长度。
CHALLENGE_SIZE = 32

#: 握手超时秒数。对端不应答时不能让连接永久悬挂。
HANDSHAKE_TIMEOUT = 10.0


class AuthenticationError(ProtocolError):
    """对端未能证明其持有共享密钥。"""


def generate_key() -> str:
    """生成共享密钥，以十六进制字符串形式返回，便于放入环境变量。"""
    return os.urandom(CHALLENGE_SIZE).hex()


def _digest(key: bytes, challenge: bytes) -> bytes:
    return hmac.new(key, challenge, hashlib.sha256).digest()


async def _exchange(reader, writer, key: bytes) -> None:
    mine = os.urandom(CHALLENGE_SIZE)
    writer.write(encode_raw(mine))
    await writer.drain()

    theirs = await read_raw(reader)
    if len(theirs) != CHALLENGE_SIZE:
        raise AuthenticationError("peer challenge has unexpected length")
    writer.write(encode_raw(_digest(key, theirs)))
    await writer.drain()

    answer = await read_raw(reader)
    if not hmac.compare_digest(answer, _digest(key, mine)):
        raise AuthenticationError("peer failed the challenge")


async def perform(reader, writer, key: str) -> None:
    """在已建立的连接上完成双向认证，失败时抛出 :class:`AuthenticationError`。"""
    key_bytes = key.encode("ascii")
    try:
        await asyncio.wait_for(_exchange(reader, writer, key_bytes), HANDSHAKE_TIMEOUT)
    except asyncio.TimeoutError as exc:
        raise AuthenticationError("handshake timed out") from exc
    except asyncio.IncompleteReadError as exc:
        raise AuthenticationError("peer closed the connection during handshake") from exc
