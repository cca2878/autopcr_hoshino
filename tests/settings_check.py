"""配置读取实测。

验证配置取自宿主框架的配置模块、环境变量的优先级、大小写宽容，
以及配置模块缺失或出错时的行为。
"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from autopcr_hoshino.hbot import settings  # noqa: E402

failures = []


def check(condition, description):
    if condition:
        print(f"  [通过] {description}")
    else:
        failures.append(description)
        print(f"  [失败] {description}")


def make_module(**values):
    """构造一个形似 hoshino/config/<模块名>.py 的配置模块。"""
    module = types.ModuleType("hoshino.config.autopcr_hoshino")
    for name, value in values.items():
        setattr(module, name, value)
    return module


def main():
    print("[1] 配置项与环境变量名的对应")
    check(
        settings.env_name("autopcr_root") == "AUTOPCR_HOSHINO_AUTOPCR_ROOT",
        "普通项加前缀并大写",
    )
    check(
        settings.env_name("autopcr_public_address") == "AUTOPCR_PUBLIC_ADDRESS",
        "沿用 autopcr 自身变量的项不加前缀",
    )
    check(
        settings.MODULE_NAME == "autopcr_hoshino",
        f"模块名取插件目录名，实得 {settings.MODULE_NAME}",
    )

    print("\n[2] 从配置模块取值")
    settings.reload(
        make_module(
            AUTOPCR_ROOT="/srv/autopcr",
            AUTO_UPDATE=True,
            RESTART_DELAY=12,
            WEB_PREFIX="/daily",
            AUTOPCR_REF="",
            AUTOPCR_PUBLIC_ADDRESS="bot.example.com",
        )
    )
    check(settings.get("autopcr_root") == "/srv/autopcr", "字符串项")
    check(settings.get_bool("auto_update", False) is True, "布尔项")
    check(settings.get_float("restart_delay", 5.0) == 12.0, "数值项")
    check(settings.get("autopcr_ref", "缺省") == "缺省", "空字符串回落到默认值")
    check(settings.get("nonexistent", "缺省") == "缺省", "未定义的项回落到默认值")

    print("\n[3] 大小写宽容")
    settings.reload(make_module(autopcr_root="/lower/case"))
    check(settings.get("autopcr_root") == "/lower/case", "接受小写写法")

    print("\n[4] 环境变量优先于配置模块")
    settings.reload(make_module(AUTOPCR_ROOT="/from/module"))
    os.environ["AUTOPCR_HOSHINO_AUTOPCR_ROOT"] = "/from/env"
    check(settings.get("autopcr_root") == "/from/env", "环境变量覆盖配置模块")
    del os.environ["AUTOPCR_HOSHINO_AUTOPCR_ROOT"]
    check(settings.get("autopcr_root") == "/from/module", "移除环境变量后回到配置模块")

    print("\n[5] 传入 wrapper 子进程的配置项")
    settings.reload(
        make_module(
            WEB_HOST="0.0.0.0",
            VERIFY_REGISTER=False,
            AUTOPCR_PUBLIC_ADDRESS="bot.example.com",
            AUTOPCR_ROOT="/srv/autopcr",
        )
    )
    env = settings.as_environment()
    check(env.get("AUTOPCR_HOSHINO_WEB_HOST") == "0.0.0.0", "网页端配置被转换为环境变量")
    check(
        env.get("AUTOPCR_HOSHINO_VERIFY_REGISTER") == "false",
        "布尔项被规范为小写后转换为环境变量",
    )
    check(
        env.get("AUTOPCR_PUBLIC_ADDRESS") == "bot.example.com",
        "沿用 autopcr 变量名的项也被转换",
    )
    check(
        "AUTOPCR_HOSHINO_AUTOPCR_ROOT" not in env,
        "仅兼容层使用的项不注入子进程",
    )
    os.environ["AUTOPCR_HOSHINO_WEB_HOST"] = "127.0.0.1"
    check(
        "AUTOPCR_HOSHINO_WEB_HOST" not in settings.as_environment(),
        "已存在的环境变量不被配置模块覆盖",
    )
    del os.environ["AUTOPCR_HOSHINO_WEB_HOST"]

    print("\n[6] 配置模块缺失时只用环境变量与默认值")
    settings.reload()
    check(settings.get("autopcr_root", "空") == "空", "缺少配置模块时取默认值")
    check("默认值" in settings.describe_source(), f"来源说明：{settings.describe_source()}")

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
