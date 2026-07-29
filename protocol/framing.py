"""帧编解码。

线格式为 4 字节大端长度前缀加载荷，载荷是 UTF-8 编码的 JSON 文本。
不使用 pickle：两端运行在刻意隔离的解释器环境中，不共享任何自定义类型，
pickle 能传任意对象这一优势无从发挥，而反序列化即执行代码的风险照单全收。
"""
import json
import struct

_HEADER = struct.Struct(">I")

#: 单帧载荷上限。结果图以 base64 CQ 码形式传输，兆字节量级属正常范围。
MAX_FRAME_SIZE = 64 * 1024 * 1024


class ProtocolError(Exception):
    """线格式错误，出现即表示连接不可信，应当断开。"""


def encode(message: dict) -> bytes:
    """把消息编码为带长度前缀的完整帧。"""
    payload = json.dumps(message, ensure_ascii=False).encode("utf-8")
    if len(payload) > MAX_FRAME_SIZE:
        raise ProtocolError(
            f"frame too large to send: {len(payload)} > {MAX_FRAME_SIZE}"
        )
    return _HEADER.pack(len(payload)) + payload


def encode_raw(payload: bytes) -> bytes:
    """把已有字节串包装成帧。握手阶段传输随机数与摘要时使用。"""
    if len(payload) > MAX_FRAME_SIZE:
        raise ProtocolError(
            f"frame too large to send: {len(payload)} > {MAX_FRAME_SIZE}"
        )
    return _HEADER.pack(len(payload)) + payload


async def read_raw(reader) -> bytes:
    """读取一个完整帧并返回其原始载荷。

    长度前缀先于载荷校验，避免对端声明一个巨大长度导致本端无限制分配内存。
    连接中断时抛出 ``asyncio.IncompleteReadError``，由调用方判定为断线。
    """
    header = await reader.readexactly(_HEADER.size)
    (size,) = _HEADER.unpack(header)
    if size > MAX_FRAME_SIZE:
        raise ProtocolError(
            f"frame too large to read: {size} > {MAX_FRAME_SIZE}"
        )
    return await reader.readexactly(size)


async def read(reader) -> dict:
    """读取一个完整帧并解析为消息对象。"""
    payload = await read_raw(reader)
    try:
        message = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ProtocolError(f"malformed frame: {exc}") from exc
    if not isinstance(message, dict):
        raise ProtocolError("frame payload must be an object")
    return message
