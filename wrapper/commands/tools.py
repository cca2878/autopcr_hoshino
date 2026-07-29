"""工具命令的参数解析器。

每个解析器读取并消费属于自己的消息记号，返回传给 autopcr 模块的配置项。
返回的配置项会覆盖账号已保存的同名配置，未提及的配置项保持账号设置不变。
"""
import re
from typing import List

from .pipeline import require_super_admin
from .registry import is_args_exist, register_tool


def recover_text_by_tokens(raw_text: str, tokens: List[str]) -> str:
    """在原始消息中定位给定记号序列，取回它们之间的原始文本。

    记号列表按空白切分，会丢失换行；而多队编队按行区分队伍，需要原始排版。
    """
    if not tokens:
        return ""
    pattern = r"\s+".join(re.escape(token) for token in tokens)
    match = re.search(pattern, raw_text, flags=re.S)
    if match:
        return raw_text[match.start():match.end()]
    return " ".join(tokens)


# ---------------------------------------------------------------- 无参数工具


@register_tool("公会支援", "get_clan_support_unit")
async def clan_support(botev):
    return {}


@register_tool("查心碎", "get_need_xinsui")
async def find_xinsui(botev):
    return {}


@register_tool("查纯净碎片", "get_need_pure_memory")
async def find_pure_memory(botev):
    return {}


@register_tool("查sp碎片", "get_need_sp_memory")
async def find_sp_memory(botev):
    return {}


@register_tool("查缺角色", "missing_unit")
async def find_missing_unit(botev):
    return {}


@register_tool("查缺称号", "missing_emblem")
async def find_missing_emblem(botev):
    return {}


@register_tool("刷新box", "refresh_box")
async def refresh_box(botev):
    return {}


@register_tool("查探险编队", "travel_team_view")
async def find_travel_team_view(botev):
    return {}


@register_tool("半月刊", "half_schedule")
async def half_schedule(botev):
    return {}


@register_tool("查深域", "find_talent_quest")
async def find_talent_quest(botev):
    return {}


@register_tool("查公会深域", "find_clan_talent_quest")
async def find_clan_talent_quest(botev):
    return {}


# ---------------------------------------------------------------- 带参数工具


@register_tool("查记忆碎片", "get_need_memory")
async def find_memory(botev):
    msg = await botev.message()
    consider_unit = "所有"
    if is_args_exist(msg, "可刷取"):
        consider_unit = "地图可刷取"
    elif is_args_exist(msg, "大师币"):
        consider_unit = "大师币商店"
    return {"memory_demand_consider_unit": consider_unit}


@register_tool("查装备", "get_need_equip")
async def find_equip(botev):
    msg = await botev.message()
    like_unit_only = is_args_exist(msg, "fav")
    start_rank = None
    try:
        start_rank = int(msg[0])
        del msg[0]
    except (IndexError, ValueError):
        pass
    return {"start_rank": start_rank, "like_unit_only": like_unit_only}


@register_tool("刷图推荐", "get_normal_quest_recommand")
async def quest_recommand(botev):
    msg = await botev.message()
    like_unit_only = is_args_exist(msg, "fav")
    start_rank = None
    try:
        start_rank = int(msg[0])
        del msg[0]
    except (IndexError, ValueError):
        pass
    return {"start_rank": start_rank, "like_unit_only": like_unit_only}


@register_tool("查ex装备", "ex_equip_info")
async def ex_equip_info(botev):
    msg = await botev.message()
    return {"ex_equip_info_cb_only": is_args_exist(msg, "会战")}


@register_tool("查兑换角色碎片", "redeem_unit_swap")
async def redeem_unit_swap(botev):
    msg = await botev.message()
    return {"redeem_unit_swap_do": is_args_exist(msg, "开换")}


@register_tool("查角色", "search_unit")
async def search_box(botev):
    from autopcr.util.pcr_data import get_id_from_name

    msg = await botev.message()
    unit_name = ""
    unit = None
    if msg:
        unit_name = msg[0]
        unit = get_id_from_name(unit_name)
        if unit:
            del msg[0]

    if not unit:
        await botev.finish(f"未知昵称{unit_name}")
    return {"search_unit_id": unit * 100 + 1}


@register_tool("查box", "get_box_table")
async def get_box_table(botev):
    from autopcr.util.pcr_data import get_id_from_name

    msg = await botev.message()
    box_all_unit = is_args_exist(msg, "所有")

    known_units = []
    unknown_units = []
    while msg:
        unit_name = msg[0]
        unit = get_id_from_name(unit_name)
        if unit:
            known_units.append(unit * 100 + 1)
        else:
            unknown_units.append(unit_name)
        del msg[0]

    if unknown_units:
        await botev.finish("未知昵称{}".format(", ".join(unknown_units)))
    if not known_units and not box_all_unit:
        await botev.finish("请指定角色或添加【所有】参数")

    return {"box_unit": known_units, "box_all_unit": box_all_unit}


@register_tool("黎明界开局", "labyrinth_start_reroll")
async def labyrinth_start_reroll(botev):
    from autopcr.db.database import db

    msg = await botev.message()
    guild_id = 0
    if msg:
        for guild in db.labyrinth_enter_guild.values():
            if msg[0] in guild.guild_name.replace(r"\n", ""):
                guild_id = guild.guild_id
                del msg[0]
                break

    if guild_id == 0:
        names = "\n".join(
            guild.guild_name.replace(r"\n", "")
            for guild in db.labyrinth_enter_guild.values()
        )
        await botev.finish("未找到公会，请输入包含以下公会名字：" + names)

    return {"labyrinth_reroll_guild_id": guild_id}


@register_tool("免费十连", "free_gacha")
async def free_gacha(botev):
    msg = await botev.message()
    gacha_id = 0
    try:
        gacha_id = int(msg[0])
        del msg[0]
    except (IndexError, ValueError):
        pass
    return {"free_gacha_select_ids": [gacha_id], "today_end_gacha_no_do": False}


@register_tool("一键编队", "set_my_party2")
async def set_my_party_multi(botev):
    raw_msg = await botev.message_raw()
    msg = await botev.message()

    tab_start_num = 1
    party_start_num = 1
    try:
        tab_start_num = int(msg[0])
        del msg[0]
    except (IndexError, ValueError):
        pass
    try:
        party_start_num = int(msg[0])
        del msg[0]
    except (IndexError, ValueError):
        pass
    is_to_max = is_args_exist(msg, "拉满")

    teams_text = recover_text_by_tokens(raw_msg, msg)
    config = {
        "tab_start_num2": tab_start_num,
        "party_start_num2": party_start_num,
        "set_my_party_text2": teams_text,
        "set_my_party2_to_max": is_to_max,
    }
    del msg[:]
    return config


@register_tool("来发十连", "gacha_start")
@require_super_admin
async def gacha_start(botev):
    from autopcr.db.database import db

    msg = await botev.message()
    pool_id = ""
    try:
        pool_id = msg[0]
        del msg[0]
    except IndexError:
        pass

    cc_until_get = is_args_exist(msg, "抽到出")
    really_do = is_args_exist(msg, "开抽")
    single_ticket = is_args_exist(msg, "单抽券")
    single = is_args_exist(msg, "单抽")
    small_first = is_args_exist(msg, "编号小优先")

    current_gacha = {gacha.split(":")[0]: gacha for gacha in db.get_cur_gacha()}
    if pool_id not in current_gacha:
        await botev.finish(f"未找到该卡池{pool_id}")
    pool_id = current_gacha[pool_id]

    if single_ticket and single:
        await botev.finish("单抽券和单抽只能选一个")

    gacha_method = "十连"
    if single_ticket:
        gacha_method = "单抽券"
    elif single:
        gacha_method = "单抽"

    if not really_do:
        lines = [f"卡池{pool_id}"]
        if cc_until_get:
            lines.append("抽到出")
        if small_first:
            lines.append("编号小优先")
        lines.append(gacha_method)
        lines.append("确认无误，消息末尾加上【开抽】即可开始抽卡")
        await botev.finish("\n".join(lines))

    return {
        "pool_id": pool_id,
        "cc_until_get": cc_until_get,
        "gacha_method": gacha_method,
        "gacha_start_auto_select_pickup_min_first": small_first,
    }
