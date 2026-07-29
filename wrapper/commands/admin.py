"""管理类命令。"""


async def query_clan_battle_forbidden(botev):
    """列出会战期间被限制为仅管理员调用的账号。"""
    from autopcr.module.accountmgr import instance as usermgr
    from autopcr.util.draw import instance as drawer
    from autopcr.util.draw_table import outp_b64

    if not await botev.is_admin():
        await botev.finish("仅管理员可以调用")

    content = ["会战期间仅管理员调用"]
    for qq in usermgr.qids():
        async with usermgr.load(qq, readonly=True) as accmgr:
            for alias in accmgr.accounts():
                async with accmgr.load(alias, readonly=True) as acc:
                    if acc.is_clan_battle_forbidden():
                        content.append(f"{acc.qq}  {acc.alias} ")

    await botev.finish(outp_b64(await drawer.draw_msgs(content)))


async def query_group_clan_battle_forbidden(botev):
    """按本群成员列出各自账号的会战调用限制。"""
    from autopcr.module.accountmgr import instance as usermgr
    from autopcr.util.draw import instance as drawer
    from autopcr.util.draw_table import outp_b64

    if not await botev.is_admin():
        await botev.finish("仅管理员可以调用")

    header = ["昵称", "QQ", "账号", "会战调用"]
    content = []
    known = set(usermgr.qids())
    for qq, name in await botev.get_group_member_list():
        if qq not in known:
            content.append([name, qq, "", ""])
            continue
        async with usermgr.load(qq, readonly=True) as accmgr:
            for alias in accmgr.accounts():
                async with accmgr.load(alias, readonly=True) as acc:
                    limited = "仅限管理员" if acc.is_clan_battle_forbidden() else ""
                    content.append([name, qq, alias, limited])

    await botev.finish(outp_b64(await drawer.draw(header, content)))


async def find_ghost(botev):
    """列出已不在任何启用群内的注册号码。"""
    from autopcr.module.accountmgr import instance as usermgr

    invalid = await botev.filter_invalid_qq(list(usermgr.qids()))
    if not invalid:
        await botev.finish("未找到内鬼")
    await botev.finish(" ".join(invalid))


async def clean_ghost(botev):
    """删除已不在任何启用群内的注册号码。"""
    from autopcr.module.accountmgr import instance as usermgr

    invalid = await botev.filter_invalid_qq(list(usermgr.qids()))
    if not invalid:
        await botev.finish("未找到内鬼")

    for qq in invalid:
        usermgr.delete(qq)
    await botev.finish(" ".join([f"已清除{len(invalid)}个内鬼:"] + invalid))


async def service_status(botev):
    """查看客户端池的占用情况。"""
    from autopcr.core.clientpool import instance as clientpool

    lines = []
    for index, (running, waiting, max_count) in enumerate(clientpool.sema_status()):
        lines.append(
            f"运行状态{index}：{running}/{max_count}正在运行，{waiting}等待中"
        )
    await botev.send("\n".join(lines))
