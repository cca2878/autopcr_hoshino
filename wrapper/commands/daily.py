"""清日常与运行记录相关命令。"""
import asyncio
import logging

from ..message import escape
from .pipeline import (
    check_final_args_be_empty,
    wrap_account,
    wrap_accountmgr,
)
from .registry import strip_prefix

logger = logging.getLogger("autopcr_hoshino.wrapper.commands")

#: 等待验证码的轮询次数，每次间隔一秒。
VALIDATE_POLL_ROUNDS = 360


async def check_validate(botev, qq: str, count: int = 1) -> None:
    """在后台等待登录验证码请求，并把认证链接发给用户。

    autopcr 在本地求解与远程求解均失败时会把一条待人工完成的认证请求放入待办表，
    本协程轮询该表并将链接转发到群内。``count`` 为需要等待的账号数量。
    """
    from autopcr.http_server.validator import validate_dict

    for _ in range(VALIDATE_POLL_ROUNDS):
        if qq in validate_dict and validate_dict[qq]:
            validate = validate_dict[qq].pop()
            if validate.status == "ok":
                del validate_dict[qq]
                count -= 1
                if not count:
                    break
                continue

            url = botev.web_address + strip_prefix(validate.url, "/daily/")
            await botev.send(
                f"pcr账号登录需要验证码，请点击以下链接在120秒内完成认证:\n{url}"
            )
        else:
            await asyncio.sleep(1)


@wrap_accountmgr
async def clean_daily_all(botev, accmgr):
    """为该号码下的全部账号清日常。"""
    from autopcr.module.modulebase import eResultStatus
    from autopcr.util.draw import instance as drawer
    from autopcr.util.draw_table import outp_b64

    loop = asyncio.get_event_loop()
    is_admin_call = await botev.is_admin()

    async def clean_one(alias: str):
        async with accmgr.load(alias) as acc:
            return await acc.do_daily(is_admin_call)

    aliases = []
    tasks = []
    for alias in accmgr.accounts():
        aliases.append(escape(alias))
        tasks.append(loop.create_task(clean_one(alias)))

    try:
        await botev.send("开始为{}清理日常".format(",".join(aliases)))
    except Exception as exc:
        logger.exception("发送开始提示失败：%r", exc)

    loop.create_task(check_validate(botev, accmgr.qid, len(aliases)))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    header = ["昵称", "清日常结果", "状态"]
    content = []
    for index, result in enumerate(results):
        if isinstance(result, Exception):
            content.append([aliases[index], str(result), "#" + eResultStatus.ERROR.value])
        else:
            content.append(
                [
                    aliases[index],
                    result.get_result().get_last_result().log,
                    "#" + result.status.value,
                ]
            )

    await botev.send(outp_b64(await drawer.draw(header, content)))


@wrap_accountmgr
@wrap_account
@check_final_args_be_empty
async def clean_daily_from(botev, acc):
    """为指定账号清日常。"""
    from autopcr.util.draw import instance as drawer
    from autopcr.util.draw_table import outp_b64

    alias = escape(acc.alias)
    try:
        await botev.send(f"开始为{alias}清理日常")
    except Exception as exc:
        logger.exception("发送开始提示失败：%r", exc)

    try:
        is_admin_call = await botev.is_admin()
        asyncio.get_event_loop().create_task(check_validate(botev, acc.qq))

        result = await acc.do_daily(is_admin_call)
        image = await drawer.draw_tasks_result(result.get_result())
        await botev.send(alias + outp_b64(image))
    except Exception as exc:
        await botev.send(f"{alias}: {exc}")


@wrap_accountmgr
@wrap_account
async def clean_daily_result(botev, acc):
    """查看最近几次的清日常报告。"""
    from autopcr.util.draw import instance as drawer
    from autopcr.util.draw_table import outp_b64

    msg = await botev.message()
    result_id = 0
    try:
        result_id = int(msg[0])
        del msg[0]
    except (IndexError, ValueError):
        pass

    result = await acc.get_daily_result_from_id(result_id)
    if not result:
        await botev.finish("未找到日常报告")
    await botev.finish(outp_b64(await drawer.draw_tasks_result(result)))


@wrap_accountmgr
async def clean_daily_time(botev, accmgr):
    """查看各账号的清日常记录。"""
    from autopcr.util.draw import instance as drawer
    from autopcr.util.draw_table import outp_b64

    content = []
    for alias in accmgr.accounts():
        async with accmgr.load(alias, readonly=True) as acc:
            content += [
                [acc.alias, item.time, "#" + item.status.value]
                for item in acc.get_daily_result_list()
            ]

    if not content:
        await botev.finish("暂无日常记录")
    header = ["昵称", "清日常时间", "状态"]
    await botev.finish(outp_b64(await drawer.draw(header, content)))
