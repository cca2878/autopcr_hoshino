"""帮助、卡池与图片识别命令。"""
from ...catalog import COMMAND_PREFIX, SV_HELP


async def show_help(botev):
    """以图片形式展示指令说明。"""
    from autopcr.util.draw import instance as drawer
    from autopcr.util.draw_table import outp_b64

    await botev.finish(outp_b64(await drawer.draw_msgs(SV_HELP.split("\n"))))


async def config_clear_daily(botev):
    """给出网页端配置地址。"""
    await botev.finish(botev.web_address + "login")


async def gacha_current(botev):
    """列出当前卡池。"""
    from autopcr.db.database import db

    await botev.finish("\n".join(db.get_mirai_gacha()))


async def ocr_team(botev):
    """识别图片中的队伍，输出可直接使用的一键编队指令。"""
    from io import BytesIO

    from autopcr.db.database import db
    from autopcr.util import aiorequests
    from autopcr.util.unit_recognizer import instance as unit_recognizer
    from PIL import Image

    image_urls = await botev.image()
    if not image_urls:
        await botev.finish("未识别到图片!")

    teams = []
    for index, url in enumerate(image_urls):
        try:
            raw = await (await aiorequests.get(url, timeout=6)).content
            image = Image.open(BytesIO(raw))
        except Exception as exc:
            await botev.send(f"图片{index + 1}下载失败: {exc}")
            continue

        box, description = await unit_recognizer.recognize(image)
        await botev.send(f"图片{index + 1}识别结果: {description}")
        if not box:
            await botev.send(f"图片{index + 1}未识别到任何队伍！")
            continue
        teams += box

    if not teams:
        await botev.finish("未识别到任何队伍！")

    lines = [COMMAND_PREFIX + "一键编队 1 1"]
    for index, team in enumerate(teams):
        names = " ".join(db.get_unit_name(unit * 100 + 1) for unit in team)
        lines.append(f"队伍{index} {names}")
    await botev.finish("\n".join(lines))
