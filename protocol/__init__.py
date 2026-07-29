"""兼容层与 wrapper 之间的进程间通信协议。

本包由两个相互隔离的解释器环境共同导入，因此只依赖标准库，
且不使用任何高于 Python 3.8 的语法。

传输为回环地址上的 TCP：兼容层监听由系统分配的端口，wrapper 启动后反向连接。
端口与共享密钥经环境变量传递，不写入文件、不经命令行、不占用标准输出。
"""
from .framing import MAX_FRAME_SIZE, ProtocolError
from .handshake import AuthenticationError, generate_key
from .handshake import perform as perform_handshake
from .peer import ConnectionClosed, Peer, RemoteError

__all__ = [
    "MAX_FRAME_SIZE",
    "ProtocolError",
    "AuthenticationError",
    "generate_key",
    "perform_handshake",
    "ConnectionClosed",
    "Peer",
    "RemoteError",
]
