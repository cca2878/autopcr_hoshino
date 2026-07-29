"""命令解析管道。

每一层从消息记号列表的头部消费属于自己的部分，把解析结果作为关键字参数传给下一层。
装饰器由外向内的顺序即命令语法，调整顺序会改变用户可以输入的格式。

工具类命令的完整形态为::

    #[导出][群]<工具名> [昵称] [工具参数...]

前三部分作用于同一个记号，因此它们是连写的。
"""
import functools
from typing import Callable

from ...catalog import COMMAND_PREFIX
from .registry import strip_prefix, tool_info


def wrap_accountmgr(func: Callable) -> Callable:
    """解析被操作的号码并加载其账号管理器。"""

    @functools.wraps(func)
    async def wrapper(botev, *args, **kwargs):
        from autopcr.module.accountmgr import instance as usermgr

        target_qq = await botev.target_qq()
        sender_qq = await botev.send_qq()

        if sender_qq != target_qq and not await botev.is_admin():
            await botev.finish("只有管理员可以操作他人账号")

        if target_qq not in usermgr.qids():
            await botev.finish(
                f"未找到{target_qq}的账号，请发送【{COMMAND_PREFIX}配置日常】进行配置"
            )

        async with usermgr.load(target_qq, readonly=True) as accmgr:
            await func(botev=botev, accmgr=accmgr, *args, **kwargs)

    return wrapper


def wrap_account(func: Callable) -> Callable:
    """解析账号昵称并加载对应账号。

    昵称可省略。省略时使用默认账号；该号码下只有一个账号时直接使用该账号。
    ``所有`` 表示该号码下的全部账号，``批量`` 表示网页端已勾选的账号。
    """

    @functools.wraps(func)
    async def wrapper(botev, accmgr, *args, **kwargs):
        from autopcr.module.accountmgr import BATCHINFO

        msg = await botev.message()

        alias = msg[0] if msg else ""
        use_all = False

        if alias == "所有":
            alias = BATCHINFO
            use_all = True
            del msg[0]
        elif alias == "批量":
            alias = BATCHINFO
            use_all = False
            del msg[0]
        elif alias not in accmgr.accounts():
            alias = accmgr.default_account
        else:
            del msg[0]

        accounts = list(accmgr.accounts())
        if alias != BATCHINFO and len(accounts) == 1:
            alias = accounts[0]

        if alias != BATCHINFO and alias not in accmgr.accounts():
            if alias:
                await botev.finish(f"未找到昵称为【{alias}】的账号")
            else:
                await botev.finish("存在多账号且未找到默认账号，请指定昵称")

        async with accmgr.load(alias, force_use_all=use_all) as acc:
            await func(botev=botev, acc=acc, *args, **kwargs)

    return wrapper


def wrap_export(func: Callable) -> Callable:
    """识别导出开关。带该前缀时结果以表格文件形式上传，而非渲染为图片。"""

    @functools.wraps(func)
    async def wrapper(botev, *args, **kwargs):
        msg = await botev.message()
        command = msg[0] if msg else ""

        export = command.startswith("导出")
        if export:
            msg[0] = strip_prefix(msg[0], "导出")

        await func(botev=botev, export=export, *args, **kwargs)

    return wrapper


def wrap_group(func: Callable) -> Callable:
    """识别群账号开关。带该前缀时操作对象为本群共用账号。"""

    @functools.wraps(func)
    async def wrapper(botev, *args, **kwargs):
        msg = await botev.message()
        command = msg[0] if msg else ""

        if command.startswith("群"):
            if not await botev.is_admin():
                await botev.finish("仅管理员可以操作群帐号")

            group_id = await botev.group_id()

            async def group_target_qq():
                return "g" + str(group_id)

            botev.target_qq = group_target_qq
            msg[0] = strip_prefix(msg[0], "群")

        await func(botev=botev, *args, **kwargs)

    return wrapper


def wrap_tool(func: Callable) -> Callable:
    """按显示名的前缀匹配定位工具。"""

    @functools.wraps(func)
    async def wrapper(botev, *args, **kwargs):
        msg = await botev.message()
        text = msg[0] if msg else ""

        for tool_name in tool_info:
            if text.startswith(tool_name):
                msg[0] = strip_prefix(msg[0], tool_name)
                if not msg[0]:
                    del msg[0]
                await func(botev=botev, tool=tool_info[tool_name], *args, **kwargs)
                return

        await botev.finish(f"未找到工具【{text}】")

    return wrapper


def wrap_config(func: Callable) -> Callable:
    """调用工具自身的解析器，得到传给模块的配置项。"""

    @functools.wraps(func)
    async def wrapper(botev, tool, *args, **kwargs):
        config = await tool.config_parser(botev)
        await func(botev=botev, tool=tool, config=config, *args, **kwargs)

    return wrapper


def check_final_args_be_empty(func: Callable) -> Callable:
    """确认全部记号均已被消费，否则提示存在无法识别的参数。"""

    @functools.wraps(func)
    async def wrapper(botev, *args, **kwargs):
        msg = await botev.message()
        if msg:
            await botev.finish("未知的参数：【" + " ".join(msg) + "】")
        await func(botev, *args, **kwargs)

    return wrapper


def require_super_admin(func: Callable) -> Callable:
    """限制只有超级管理员才能对他人账号执行。"""

    @functools.wraps(func)
    async def wrapper(botev, *args, **kwargs):
        if (
            await botev.target_qq() != await botev.send_qq()
            and not await botev.is_super_admin()
        ):
            await botev.finish("仅超级管理员调用他人")
        return await func(botev=botev, *args, **kwargs)

    return wrapper
