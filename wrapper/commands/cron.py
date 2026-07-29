"""定时任务的日志与统计命令。"""
import datetime
from collections import Counter

from .registry import is_args_exist

#: 定时日志单次展示的最大条数。
LOG_DISPLAY_LIMIT = 40


def _read_cron_logs():
    from autopcr.module.crons import CRONLOG_PATH, CronLog

    with open(CRONLOG_PATH) as fp:
        return [CronLog.from_json(line.strip()) for line in fp.readlines()]


async def cron_log(botev):
    """查看定时任务日志，可按状态与日期筛选。"""
    from autopcr.module.modulebase import eResultStatus
    from autopcr.util.draw import instance as drawer
    from autopcr.util.draw_table import outp_b64

    logs = _read_cron_logs()
    args = await botev.message()
    now = datetime.datetime.now()

    if is_args_exist(args, "错误"):
        logs = [log for log in logs if log.status == eResultStatus.ERROR]
    if is_args_exist(args, "警告"):
        logs = [log for log in logs if log.status == eResultStatus.WARNING]
    if is_args_exist(args, "成功"):
        logs = [log for log in logs if log.status == eResultStatus.SUCCESS]
    if is_args_exist(args, "昨日"):
        now -= datetime.timedelta(days=1)
        logs = [log for log in logs if log.time.date() == now.date()]
    if is_args_exist(args, "今日"):
        logs = [log for log in logs if log.time.date() == now.date()]

    lines = [str(log) for log in reversed(logs[-LOG_DISPLAY_LIMIT:])]
    if not lines:
        lines.append("暂无定时日志")
    await botev.finish(outp_b64(await drawer.draw_msgs(lines)))


async def cron_status(botev):
    """查看当日定时任务的启动与完成情况。"""
    from autopcr.module.crons import eCronOperation
    from autopcr.util.draw import instance as drawer
    from autopcr.util.draw_table import outp_b64

    logs = _read_cron_logs()
    args = await botev.message()
    now = datetime.datetime.now()
    if is_args_exist(args, "昨日"):
        now -= datetime.timedelta(days=1)

    started = [
        log
        for log in logs
        if log.operation == eCronOperation.START and log.time.date() == now.date()
    ]
    finished = [
        log
        for log in logs
        if log.operation == eCronOperation.FINISH and log.time.date() == now.date()
    ]

    lines = [f"今日定时任务：启动{len(started)}个，完成{len(finished)}个"]
    lines += [
        f"{status.value}: {count}"
        for status, count in Counter(log.status for log in finished).items()
    ]
    await botev.finish(outp_b64(await drawer.draw_msgs(lines)))


async def cron_statistic(botev):
    """按时间点统计已配置的定时任务数量。"""
    from autopcr.module.accountmgr import instance as usermgr
    from autopcr.util.draw import instance as drawer
    from autopcr.util.draw_table import outp_b64

    totals = Counter()
    clan_battle_totals = Counter()

    for qq in usermgr.qids():
        async with usermgr.load(qq, readonly=True) as accmgr:
            for alias in accmgr.accounts():
                async with accmgr.load(alias, readonly=True) as acc:
                    for index in range(1, 5):
                        suffix = f"cron{index}"
                        if not acc.data.config.get(suffix, False):
                            continue
                        moment = acc.data.config.get("time_" + suffix, "00:00")
                        if moment.count(":") == 2:
                            moment = ":".join(moment.split(":")[:2])
                        totals[moment] += 1
                        if acc.data.config.get("clanbattle_run_" + suffix, False):
                            clan_battle_totals[moment] += 1

    content = sorted(
        [[moment, str(count), str(clan_battle_totals[moment])] for moment, count in totals.items()],
        key=lambda row: row[0],
    )
    content.append(
        ["总计", str(sum(totals.values())), str(sum(clan_battle_totals.values()))]
    )
    header = ["时间", "定时任务数", "公会战任务数"]
    await botev.finish(outp_b64(await drawer.draw(header, content)))
