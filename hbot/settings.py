"""配置读取。

配置写在宿主框架的配置目录中，即 ``hoshino/config/<模块名>.py``，与其他插件一致。
模块名就是本插件在 ``MODULES_ON`` 中登记的名字。仓库内的 ``_config_example.py``
是该文件的模板。

配置项为模块级变量，名称使用大写，例如::

    AUTOPCR_ROOT = "/srv/autopcr"
    AUTO_UPDATE = True

取值优先级从高到低为：环境变量、配置模块、内置默认值。
对应的环境变量名为配置项名加 ``AUTOPCR_HOSHINO_`` 前缀。
wrapper 在独立进程中运行，其配置经环境变量传入。

配置模块不存在时只使用环境变量与默认值，与宿主框架对缺失配置的处理一致。
"""
import importlib
import logging
import os
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("autopcr_hoshino.settings")

#: 环境变量名的公共前缀。
ENV_PREFIX = "AUTOPCR_HOSHINO_"

#: 沿用 autopcr 自身环境变量名的配置项，其环境变量不加上述前缀。
_AUTOPCR_OWN_NAMES = ("AUTOPCR_PUBLIC_ADDRESS", "AUTOPCR_USE_HTTPS")

#: 本插件的模块名，即插件目录名。
MODULE_NAME = Path(__file__).resolve().parent.parent.name

_module = None  # type: Optional[object]
_loaded = False
_source = "内置默认值与环境变量"


def _config_module():
    """宿主框架配置目录中的本插件配置模块，不存在时为 ``None``。"""
    global _module, _loaded, _source
    if _loaded:
        return _module
    _loaded = True
    try:
        _module = importlib.import_module("hoshino.config." + MODULE_NAME)
        _source = f"hoshino/config/{MODULE_NAME}.py"
        logger.info("已读取配置：%s", _source)
    except ImportError:
        _module = None
        _source = "内置默认值与环境变量"
        logger.info("未找到 hoshino/config/%s.py，使用默认值与环境变量", MODULE_NAME)
    except Exception as exc:
        # 配置模块自身有错时不应连带影响插件加载。
        _module = None
        _source = f"内置默认值与环境变量（配置模块有错：{exc}）"
        logger.error("配置模块 %s 无法加载：%s", MODULE_NAME, exc)
    return _module


def reload(module=None) -> None:
    """重新读取配置。传入模块对象可直接指定配置来源。"""
    global _module, _loaded, _source
    if module is None:
        _module = None
        _loaded = False
        _source = "内置默认值与环境变量"
        _config_module()
    else:
        _module = module
        _loaded = True
        _source = "显式指定的配置模块"


def describe_source() -> str:
    """配置来源的说明，供日志与排障使用。"""
    _config_module()
    return _source


def env_name(key: str) -> str:
    """配置项对应的环境变量名。"""
    upper = key.upper()
    if upper in _AUTOPCR_OWN_NAMES:
        return upper
    return ENV_PREFIX + upper


def _from_module(key: str) -> Optional[str]:
    """从配置模块取值。

    优先按大写名查找，同时接受小写写法，以免因大小写不符而静默失效。
    """
    module = _config_module()
    if module is None:
        return None
    for name in (key.upper(), key.lower()):
        if hasattr(module, name):
            value = getattr(module, name)
            if isinstance(value, bool):
                # 规范为小写：这些值会经环境变量传给 autopcr，
                # 其布尔解析接受的字面量以小写形式给出最为稳妥。
                return "true" if value else "false"
            return "" if value is None else str(value)
    return None


def get(key: str, default: str = "") -> str:
    """按环境变量、配置模块、默认值的顺序取值。

    空值视为未设置：把配置项写成空字符串与不写该项意图相同，均回落到默认值。
    """
    from_env = os.getenv(env_name(key))
    if from_env is not None and from_env.strip():
        return from_env.strip()
    from_module = _from_module(key)
    if from_module is not None and from_module.strip():
        return from_module.strip()
    return default


def get_bool(key: str, default: bool) -> bool:
    raw = get(key, "true" if default else "false").lower()
    return raw not in ("0", "false", "no", "off", "")


def get_float(key: str, default: float) -> float:
    try:
        return float(get(key, str(default)))
    except ValueError:
        logger.warning("配置项 %s 不是数字，改用默认值 %s", key, default)
        return default


def get_int(key: str, default: int) -> int:
    try:
        return int(get(key, str(default)))
    except ValueError:
        logger.warning("配置项 %s 不是整数，改用默认值 %s", key, default)
        return default


#: 需要传给 wrapper 子进程的配置项。
#: wrapper 在独立进程中运行，其配置经环境变量传入，因此这些项须在启动子进程时注入。
WRAPPER_KEYS = (
    "web_host",
    "web_port",
    "web_backlog",
    "verify_register",
    "enable_autopcr",
    "autopcr_public_address",
    "autopcr_use_https",
)


def as_environment() -> Dict[str, str]:
    """把配置模块中与 wrapper 相关的项转换为环境变量。

    已存在的环境变量不被覆盖，以保持环境变量优先。
    空值不注入：置空的环境变量与未设置不同，会覆盖掉取值时的默认值。
    """
    result = {}
    for key in WRAPPER_KEYS:
        name = env_name(key)
        if os.getenv(name):
            continue
        value = _from_module(key)
        if value is not None and value.strip():
            result[name] = value.strip()
    return result
