"""命令分发。

兼容层把触发本次事件的命令名一并送来，据此选择对应实现。
命令名与 :mod:`catalog` 中登记的触发器一一对应。
"""
from ...catalog import COMMAND_PREFIX
from . import (
    admin,
    cron,
    daily,
    misc,
    tool_runner,
    tools,  # noqa: F401  导入即完成全部工具的注册
)

#: 命令名到实现的映射。``COMMAND_PREFIX`` 是兜底项，承接全部工具命令。
DISPATCH_TABLE = {
    "帮助自动清日常": misc.show_help,
    COMMAND_PREFIX + "帮助": misc.show_help,
    COMMAND_PREFIX + "清日常所有": daily.clean_daily_all,
    COMMAND_PREFIX + "清日常": daily.clean_daily_from,
    COMMAND_PREFIX + "日常报告": daily.clean_daily_result,
    COMMAND_PREFIX + "日常记录": daily.clean_daily_time,
    COMMAND_PREFIX + "查禁用": admin.query_clan_battle_forbidden,
    COMMAND_PREFIX + "查群禁用": admin.query_group_clan_battle_forbidden,
    COMMAND_PREFIX + "查内鬼": admin.find_ghost,
    COMMAND_PREFIX + "清内鬼": admin.clean_ghost,
    COMMAND_PREFIX + "运行状态": admin.service_status,
    COMMAND_PREFIX + "定时日志": cron.cron_log,
    COMMAND_PREFIX + "定时状态": cron.cron_status,
    COMMAND_PREFIX + "定时统计": cron.cron_statistic,
    COMMAND_PREFIX + "配置日常": misc.config_clear_daily,
    COMMAND_PREFIX + "卡池": misc.gacha_current,
    COMMAND_PREFIX + "识图": misc.ocr_team,
    COMMAND_PREFIX: tool_runner.tool_used,
}


async def dispatch(command: str, botev) -> None:
    """执行与命令名对应的实现。"""
    handler = DISPATCH_TABLE.get(command)
    if handler is None:
        raise ValueError(f"未登记的命令：{command}")
    await handler(botev)
