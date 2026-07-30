"""宿主框架加载实测。

在装有宿主框架依赖的解释器（Python 3.8）中运行，在临时目录中搭建一份最小的
HoshinoBot 部署，把本项目作为模块加载，验证：

* 项目能被宿主框架的模块加载流程正常导入。
* 服务与全部命令触发器完成注册。
* 前缀触发器按最长前缀匹配，兜底前缀不会抢走更具体的命令。
* 网页端转发端点已挂载到宿主框架的应用上。

搭建过程不改动参考仓库，全部文件写入临时目录。
"""
import os
import shutil
import sys
import tempfile

HOSHINO_SOURCE = "/workspaces/go-autopcr/ref/HoshinoBot"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_NAME = os.path.basename(PROJECT_ROOT)

#: 配置文件中使用的非默认路径前缀，用于检验配置确实生效。
CUSTOM_WEB_PREFIX = "/pcrdaily"

failures = []


def check(condition, description):
    if condition:
        print(f"  [通过] {description}")
    else:
        failures.append(description)
        print(f"  [失败] {description}")


def build_deployment(root):
    """在临时目录中搭建一份可加载的最小部署。"""
    shutil.copytree(os.path.join(HOSHINO_SOURCE, "hoshino"), os.path.join(root, "hoshino"))

    config_dir = os.path.join(root, "hoshino", "config")
    shutil.copytree(os.path.join(root, "hoshino", "config_example"), config_dir)

    bot_config = os.path.join(config_dir, "__bot__.py")
    with open(bot_config) as fp:
        text = fp.read()
    marker = "MODULES_ON = {"
    head = text[: text.index(marker)]
    with open(bot_config, "w") as fp:
        fp.write(head + "MODULES_ON = {'" + PROJECT_NAME + "'}\n")

    # 按宿主框架的惯例放一份插件配置，用非默认值以便检验其确实生效。
    with open(os.path.join(config_dir, PROJECT_NAME + ".py"), "w") as fp:
        fp.write(f'WEB_PREFIX = "{CUSTOM_WEB_PREFIX}"\n')
        fp.write("AUTO_PROVISION = False\n")

    # 以软链接引入项目本体，避免复制两套虚拟环境。
    os.symlink(PROJECT_ROOT, os.path.join(root, "hoshino", "modules", PROJECT_NAME))
    return root


def make_fake_source():
    """在项目目录内放一个形似 autopcr 源码的目录，用于检验它不会被加载。

    返回需要在测试结束时清理的路径，源码已存在时返回 ``None``。
    """
    fake = os.path.join(PROJECT_ROOT, ".autopcr")
    if os.path.exists(fake):
        return None
    os.makedirs(os.path.join(fake, "autopcr"))
    with open(os.path.join(fake, "__init__.py"), "w") as fp:
        fp.write("raise RuntimeError('该目录不应被宿主框架导入')\n")
    return fake


def main():
    # 宿主框架的工具模块会导入 matplotlib，其默认后端在无图形界面的环境中不可用。
    os.environ.setdefault("MPLBACKEND", "Agg")

    fake_source = make_fake_source()
    try:
        return run(fake_source)
    finally:
        if fake_source:
            shutil.rmtree(fake_source, ignore_errors=True)


def run(fake_source):
    root = build_deployment(tempfile.mkdtemp(prefix="hoshino-load-"))
    sys.path.insert(0, root)
    os.chdir(root)

    print("[1] 加载宿主框架并导入本项目")
    print(f"  解释器 {sys.version.split()[0]}")

    import hoshino

    hoshino.init()
    check(True, "宿主框架初始化完成且模块加载未抛异常")

    print("\n[2] 服务注册")
    from hoshino.service import _loaded_services

    service = _loaded_services.get("自动清日常")
    check(service is not None, "服务「自动清日常」已注册")

    print("\n[3] 命令触发器注册")
    import importlib

    from hoshino import trigger

    # 从宿主框架实际加载的位置读取命令清单，与运行时保持一致。
    catalog = importlib.import_module(f"hoshino.modules.{PROJECT_NAME}.catalog")
    FULLMATCH_COMMANDS = catalog.FULLMATCH_COMMANDS
    PREFIX_COMMANDS = catalog.PREFIX_COMMANDS

    missing = [c for c in PREFIX_COMMANDS if c not in trigger.prefix.trie]
    check(not missing, f"全部前缀触发器已注册，缺失 {missing}")
    # 全字命令同样登记在前缀树中，由一层包装校验前缀剥离后不得有剩余内容。
    missing = [c for c in FULLMATCH_COMMANDS if c not in trigger.prefix.trie]
    check(not missing, f"全部全字触发器已注册，缺失 {missing}")

    print("\n[4] 前缀匹配优先级")
    # 宿主框架按最长前缀匹配，具体命令优先于兜底前缀。
    cases = [
        ("#清日常所有", "#清日常所有"),
        ("#清日常 小号", "#清日常"),
        ("#查装备 11 fav", "#"),
        ("#导出群查装备", "#"),
        ("#帮助", "#帮助"),
    ]
    for text, expected in cases:
        item = trigger.prefix.trie.longest_prefix(text)
        check(
            item.key == expected,
            f"「{text}」匹配到 {expected}，实得 {item.key}",
        )

    print("\n[5] 自动准备的源码目录不被当作插件加载")
    # autopcr 仓库根目录带有 __init__.py，若其目录名不以点开头就会被宿主框架导入。
    loaded = [name for name in sys.modules if PROJECT_NAME in name and "autopcr" in name]
    check(
        not any(name.endswith(".autopcr") for name in loaded),
        "源码目录未出现在已加载模块中",
    )

    print("\n[6] 宿主框架配置目录中的配置生效")
    plugin_settings = importlib.import_module(
        f"hoshino.modules.{PROJECT_NAME}.hbot.settings"
    )
    check(
        plugin_settings.get("web_prefix", "/daily") == CUSTOM_WEB_PREFIX,
        f"配置项被读取，web_prefix 实得 {plugin_settings.get('web_prefix', '/daily')}",
    )
    check(
        f"config/{PROJECT_NAME}.py" in plugin_settings.describe_source(),
        f"配置来源指向宿主框架配置目录：{plugin_settings.describe_source()}",
    )

    print("\n[7] 网页端转发端点按配置挂载")
    import nonebot

    app = nonebot.get_bot().server_app
    rules = [str(rule) for rule in app.url_map.iter_rules()]
    matched = [r for r in rules if CUSTOM_WEB_PREFIX in r]
    check(bool(matched), f"转发端点使用配置的前缀，实测规则 {matched}")
    check(
        not any(r == "/daily" for r in rules),
        "未使用默认前缀挂载",
    )

    print("\n" + "=" * 56)
    if failures:
        print(f"失败 {len(failures)} 项：")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("全部检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
