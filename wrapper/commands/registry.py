"""工具注册表。

每个工具由一个显示名、一个 autopcr 模块键与一个参数解析器构成。
解析器从消息记号中读取并**就地删除**它所消费的记号，返回值即传给模块的配置项。
未被任何解析器消费的记号会在管道末端触发提示，据此发现拼写错误的参数。
"""
from typing import Any, Callable, Coroutine, Dict


class ToolInfo:
    """一个可由群消息触发的 autopcr 模块。"""

    __slots__ = ("name", "key", "config_parser")

    def __init__(self, name: str, key: str, config_parser):
        self.name = name
        self.key = key
        self.config_parser = config_parser


#: 显示名到工具的映射，按注册顺序排列。
tool_info: Dict[str, ToolInfo] = {}


def register_tool(name: str, key: str) -> Callable:
    """把一个参数解析器注册为工具。"""

    def decorator(func: Callable[..., Coroutine[Any, Any, Any]]):
        tool_info[name] = ToolInfo(name=name, key=key, config_parser=func)
        return func

    return decorator


def is_args_exist(msg, key: str) -> bool:
    """检查并消费一个开关式记号。"""
    if key in msg:
        msg.remove(key)
        return True
    return False


def strip_prefix(text: str, prefix: str) -> str:
    """去掉字符串开头的指定前缀。

    不能用 ``str.lstrip``：其参数是字符集合而非前缀，
    ``"validate?id=x".lstrip("/daily/")`` 会把开头的 v、a、l、i、d 一并去掉。
    """
    if prefix and text.startswith(prefix):
        return text[len(prefix):]
    return text
