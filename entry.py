"""宿主框架的加载入口。

HoshinoBot 会导入插件目录下的每一个模块，本模块被导入时完成服务与命令的注册。
"""
from .hbot.plugin import setup

sv = setup()

__all__ = ["sv"]
