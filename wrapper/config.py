"""wrapper 配置。

进程间通信所需的端口与密钥由兼容层通过环境变量注入，属于必填项。
其余配置项用于控制 autopcr 网页端的监听地址。
"""
import os


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"缺少环境变量 {name}。wrapper 需由兼容层启动，不能单独运行。"
        )
    return value


def rpc_port() -> int:
    return int(_require("AUTOPCR_HOSHINO_RPC_PORT"))


def rpc_key() -> str:
    return _require("AUTOPCR_HOSHINO_RPC_KEY")


#: autopcr 网页端的监听地址。默认只监听回环地址，由兼容层反向代理对外提供服务。
WEB_HOST = os.getenv("AUTOPCR_HOSHINO_WEB_HOST", "127.0.0.1")

#: 网页端监听端口。取 0 时由系统分配，实际端口在启动后上报给兼容层。
WEB_PORT = int(os.getenv("AUTOPCR_HOSHINO_WEB_PORT", "0"))

#: 网页端监听队列长度。
WEB_BACKLOG = int(os.getenv("AUTOPCR_HOSHINO_WEB_BACKLOG", "128"))

#: 是否要求注册者所用号码在机器人所在的群内。
VERIFY_REGISTER = os.getenv("AUTOPCR_HOSHINO_VERIFY_REGISTER", "true").lower() not in (
    "0",
    "false",
    "no",
)

#: 是否启动 autopcr。关闭后 wrapper 仅提供通信能力，用于验证与排障。
AUTOPCR_ENABLED = os.getenv("AUTOPCR_HOSHINO_ENABLE_AUTOPCR", "true").lower() not in (
    "0",
    "false",
    "no",
)
