"""兼容层配置。

取值来源与优先级见 :mod:`autopcr_hoshino.hbot.settings`。
兼容层运行在宿主框架的解释器中，因此这里不得导入 wrapper 或 autopcr 的任何模块。

需要在运行时读取的项以函数形式提供，使宿主框架的加载顺序不影响取值。
"""
from pathlib import Path

from . import settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: 本项目的包名。wrapper 以 ``python -m <包名>.wrapper`` 启动，
#: 使其内部的相对导入与在宿主框架中被加载时保持一致。
PACKAGE_NAME = PROJECT_ROOT.name


# ---------------------------------------------------------------- 自动准备


def auto_provision() -> bool:
    """未指定 autopcr 位置时，是否自动取得源码并准备运行环境。"""
    return settings.get_bool("auto_provision", True)


def autopcr_repo() -> str:
    """自动准备时使用的仓库地址。"""
    return settings.get("autopcr_repo", "https://github.com/cc004/autopcr")


def autopcr_ref() -> str:
    """自动准备时检出的分支或标签，留空则使用远端默认分支。"""
    return settings.get("autopcr_ref")


def auto_update() -> bool:
    """每次启动时是否尝试更新已取得的源码。

    默认关闭：上游改动在无人值守时生效的风险高于收益。
    """
    return settings.get_bool("auto_update", False)


def managed_root() -> str:
    """自动准备时源码的存放位置。账号数据与母数据位于其下的 cache 目录。

    默认值以点开头：宿主框架会导入插件目录下的每一个子目录，
    而 autopcr 仓库根目录带有 ``__init__.py``，普通名字会被误当作插件。
    """
    return settings.get("managed_root", str(PROJECT_ROOT / ".autopcr"))


def managed_venv() -> str:
    """自动准备时运行环境的存放位置。"""
    return settings.get("managed_venv", str(PROJECT_ROOT / ".venv-autopcr"))


def autopcr_python_version() -> str:
    """自动准备运行环境时使用的 Python 版本。"""
    return settings.get("autopcr_python_version", "3.10")


# ---------------------------------------------------------------- 自行管理


def wrapper_python() -> str:
    """运行 wrapper 的解释器。该解释器所在环境需安装 autopcr 的依赖。"""
    return settings.get(
        "python", str(PROJECT_ROOT / ".venv-autopcr" / "bin" / "python")
    )


def autopcr_root() -> str:
    """autopcr 源码根目录，即包含 ``autopcr`` 包的那一层。

    指定该项即视为使用者自行管理环境，自动准备不再进行。
    """
    return settings.get("autopcr_root")


# ---------------------------------------------------------------- 进程与网络


def restart_delay() -> float:
    """wrapper 意外退出后的重启间隔秒数。连续失败时按倍数延长。"""
    return settings.get_float("restart_delay", 5.0)


def max_restart_delay() -> float:
    """重启间隔的上限秒数。"""
    return settings.get_float("max_restart_delay", 300.0)


def healthy_uptime() -> float:
    """一次运行持续超过该秒数即视为正常，重启间隔随之重置。"""
    return settings.get_float("healthy_uptime", 60.0)


def startup_timeout() -> float:
    """等待 wrapper 建立连接并完成认证的秒数。"""
    return settings.get_float("startup_timeout", 180.0)


def web_proxy_enabled() -> bool:
    """是否在宿主框架上提供 autopcr 网页端的转发。"""
    return settings.get_bool("web_proxy", True)


def web_path_prefix() -> str:
    """转发网页端时使用的路径前缀，需与 autopcr 自身的前缀一致。"""
    return settings.get("web_prefix", "/daily")
