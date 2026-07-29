"""工具命令的统一入口。

承接所有未被更具体的命令匹配的消息，由解析管道逐层确定工具、账号与配置项后执行。
"""
import asyncio
import datetime
import logging

from ..message import escape
from .daily import check_validate
from .pipeline import (
    check_final_args_be_empty,
    wrap_account,
    wrap_accountmgr,
    wrap_config,
    wrap_export,
    wrap_group,
    wrap_tool,
)

logger = logging.getLogger("autopcr_hoshino.wrapper.commands")

#: 上传结果表格时使用的群文件夹名。
EXPORT_FOLDER = "autopcr"


@wrap_export
@wrap_group
@wrap_tool
@wrap_accountmgr
@wrap_account
@wrap_config
@check_final_args_be_empty
async def tool_used(botev, tool, config, acc, export):
    from autopcr.db.database import db
    from autopcr.util.draw import instance as drawer
    from autopcr.util.draw_table import outp_b64
    from autopcr.util.excel_export import export_excel

    alias = escape(acc.alias)
    try:
        asyncio.get_event_loop().create_task(check_validate(botev, acc.qq))

        is_admin_call = await botev.is_admin()
        await botev.send(f"开始为{alias}执行【{tool.name}】")
        result = await acc.do_from_key(config, tool.key, is_admin_call)

        # 批量模式返回逐账号的结果列表，其首项已由 autopcr 汇总为整体结果。
        if isinstance(result, list):
            if not result:
                await botev.send("未选择账号！请到网页端批量运行选择账号后运行")
                return
            result = result[0]

        result = result.get_result()
        if export:
            data = await export_excel(result.table)
            timestamp = db.format_time_safe(datetime.datetime.now())
            filename = f"{tool.name}_{alias}_{timestamp}.xlsx"
            await botev.upload_file(data.getvalue(), filename, EXPORT_FOLDER)
        else:
            image = await drawer.draw_task_result(result)
            await botev.send(alias + outp_b64(image))
    except Exception as exc:
        logger.exception("执行工具 %s 失败", tool.name)
        await botev.send(f"{alias}: {exc}")
