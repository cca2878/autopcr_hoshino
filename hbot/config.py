"""兼容层配置。

全部配置项通过环境变量提供，未设置时取默认值。
兼容层运行在宿主框架的解释器中，因此这里不得导入 wrapper 或 autopcr 的任何模块。
"""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: 本项目的包名。wrapper 以 ``python -m <包名>.wrapper`` 启动，
#: 使其内部的相对导入与在宿主框架中被加载时保持一致。
PACKAGE_NAME = PROJECT_ROOT.name


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def wrapper_python() -> str:
    """运行 wrapper 的解释器。该解释器所在环境需安装 autopcr 的依赖。"""
    return _env(
        "AUTOPCR_HOSHINO_PYTHON", str(PROJECT_ROOT / ".venv-autopcr" / "bin" / "python")
    )


def autopcr_root() -> str:
    """autopcr 源码根目录，即包含 ``autopcr`` 包的那一层。"""
    return _env("AUTOPCR_HOSHINO_AUTOPCR_ROOT")


# 以上两项在每次启动子进程时读取，而非在导入时固化，
# 使宿主框架的加载顺序不影响取值。

#: wrapper 意外退出后的重启间隔秒数。连续失败时按倍数延长，直至 :data:`MAX_RESTART_DELAY`。
RESTART_DELAY = float(_env("AUTOPCR_HOSHINO_RESTART_DELAY", "5"))

#: 重启间隔的上限秒数。
MAX_RESTART_DELAY = float(_env("AUTOPCR_HOSHINO_MAX_RESTART_DELAY", "300"))

#: 一次运行持续超过该秒数即视为正常，重启间隔随之重置。
HEALTHY_UPTIME = float(_env("AUTOPCR_HOSHINO_HEALTHY_UPTIME", "60"))

#: 等待 wrapper 建立连接并完成认证的秒数。
STARTUP_TIMEOUT = float(_env("AUTOPCR_HOSHINO_STARTUP_TIMEOUT", "180"))

#: 反向代理转发 autopcr 网页端时使用的路径前缀，需与 autopcr 自身的前缀一致。
WEB_PATH_PREFIX = _env("AUTOPCR_HOSHINO_WEB_PREFIX", "/daily")

#: 是否启用网页端反向代理。关闭后用户需直接访问 wrapper 监听的端口。
WEB_PROXY_ENABLED = _env("AUTOPCR_HOSHINO_WEB_PROXY", "true").lower() not in (
    "0",
    "false",
    "no",
)

#: 转发给 wrapper 的额外环境变量名。autopcr 自身的配置项由此透传。
PASSTHROUGH_ENV_PREFIXES = ("AUTOPCR_",)
