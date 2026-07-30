"""自动准备测试。

在装有宿主框架依赖的解释器（Python 3.8）中运行，从零开始取得 autopcr 源码、
创建运行环境并安装依赖，最后拉起 wrapper 验证其可用，据此确认部署只需放好插件目录。

全部产物写入临时目录，不影响既有环境。首次运行需下载源码与依赖，耗时较长。
设置 ``AUTOPCR_HOSHINO_PROVISION_FROM`` 可改为从本地仓库克隆，避免依赖外网。
"""
import asyncio
import os
import pathlib
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

failures = []


def check(condition, description):
    if condition:
        print(f"  [通过] {description}")
    else:
        failures.append(description)
        print(f"  [失败] {description}")


async def handle_callback(method, params):
    return None


async def main():
    from autopcr_hoshino.hbot import config, provision
    from autopcr_hoshino.hbot.supervisor import Supervisor

    workspace = tempfile.mkdtemp(prefix="provision-check-")
    # 默认从上游仓库克隆；指定本地仓库可避免依赖外网。
    source_repo = os.getenv("AUTOPCR_HOSHINO_PROVISION_FROM", "").strip()
    if not source_repo:
        local = os.path.join(os.path.dirname(PROJECT_ROOT), "ref", "autopcr_latest")
        source_repo = local if os.path.isdir(local) else config.autopcr_repo()

    # 准备目标与解释器位置都指向临时目录，避免动到既有环境。
    os.environ["AUTOPCR_HOSHINO_AUTOPCR_REPO"] = source_repo
    os.environ["AUTOPCR_HOSHINO_MANAGED_ROOT"] = os.path.join(workspace, "autopcr")
    os.environ["AUTOPCR_HOSHINO_MANAGED_VENV"] = os.path.join(workspace, "venv")
    os.environ.pop("AUTOPCR_HOSHINO_AUTOPCR_ROOT", None)
    os.environ.pop("AUTOPCR_HOSHINO_PYTHON", None)
    os.environ["AUTOPCR_HOSHINO_ENABLE_AUTOPCR"] = "false"

    print("[1] 外部程序可用性")
    print(f"  {provision.describe_requirements()}")
    check(provision.find_executable("git") is not None, "git 可用")
    check(provision.is_managed(), "未指定 autopcr 位置时判定为自动准备")

    try:
        print("\n[2] 取得源码并创建运行环境")
        source, python = await provision.provision()
        check(provision.is_valid_source(pathlib.Path(source)), f"源码已就位于 {source}")
        check(os.path.exists(python), f"解释器已就位于 {python}")

        version = await provision._run_checked(
            [python, "-c", "import sys;print(sys.version.split()[0])"]
        )
        check(version.startswith("3.10"), f"解释器版本为 {version}")

        # Quart 0.19 不提供 __version__ 属性，版本需从包元数据读取。
        probe = await provision._run_checked(
            [
                python,
                "-c",
                "import importlib.metadata as m, quart, PIL, gtlv;print(m.version('Quart'))",
            ]
        )
        check(probe.startswith("0.19"), f"依赖已安装，Quart {probe}")

        print("\n[3] 重复准备应当跳过已完成的步骤")
        again_source, again_python = await provision.provision()
        check(again_source == source and again_python == python, "重复准备结果一致")

        print("\n[4] 用自动准备的环境拉起 wrapper")
        supervisor = Supervisor(handle_callback, provisioner=provision.provision)
        await supervisor.start()
        check(await supervisor.wait_ready(120), "wrapper 完成连接与认证")
        if supervisor.alive:
            pong = await supervisor.call("ping")
            check(pong.get("ready") is True, "自动准备的环境可正常运行 wrapper")
        await supervisor.stop()
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    print("\n" + "=" * 56)
    if failures:
        print(f"失败 {len(failures)} 项：")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("全部检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.get_event_loop().run_until_complete(main()))
