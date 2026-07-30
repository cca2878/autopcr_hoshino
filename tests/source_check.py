"""源码识别与数据位置测试。

网络受限时使用者需自行下载 autopcr 源码放置到位，本测试验证：

* 自行放置的源码即使不是 git 仓库也被接受，且不因此要求 git 可用。
* 目录内容不完整时给出缺失清单；源码多套一层目录时指出实际位置。
* 已放置的源码不被改动，其中的运行数据不被触碰。
* autopcr 自带的 server.py 不会被误当作宿主框架的插件加载。
"""
import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from autopcr_hoshino.hbot import provision  # noqa: E402

failures = []


def check(condition, description):
    if condition:
        print(f"  [通过] {description}")
    else:
        failures.append(description)
        print(f"  [失败] {description}")


def make_source(root: Path, with_git: bool = False, nested: str = "") -> Path:
    """造一份形似 autopcr 源码的目录，只含判定所依据的文件。"""
    base = root / nested if nested else root
    for marker in provision.SOURCE_MARKERS:
        target = base / marker
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# 占位\n", encoding="utf-8")
    # autopcr 源码根目录带有 __init__.py 与 server.py，二者都不应被宿主框架导入。
    (base / "__init__.py").write_text("## nothing\n", encoding="utf-8")
    (base / "server.py").write_text(
        "raise RuntimeError('autopcr 自带的 server.py 不应被导入')\n", encoding="utf-8"
    )
    if with_git:
        (base / ".git").mkdir()
    return base


async def main():
    workspace = Path(tempfile.mkdtemp(prefix="source-check-"))
    try:
        print("[1] 自行放置的源码被接受")
        placed = workspace / "placed"
        make_source(placed)
        check(provision.is_valid_source(placed), "识别为可用源码")
        check(not (placed / ".git").exists(), "该源码不是 git 仓库")
        source = await provision.ensure_source(placed)
        check(source == placed, "直接使用而未尝试克隆")

        print("\n[2] 运行数据不被触碰")
        data = placed / "cache" / "http_server"
        data.mkdir(parents=True)
        marker = data / "account.json"
        marker.write_text("账号配置", encoding="utf-8")
        await provision.ensure_source(placed)
        check(marker.read_text(encoding="utf-8") == "账号配置", "cache 中的内容保持原样")

        print("\n[3] 内容不完整时的提示")
        broken = workspace / "broken"
        (broken / "autopcr").mkdir(parents=True)
        check(not provision.is_valid_source(broken), "不完整的目录不被识别为源码")
        try:
            await provision.ensure_source(broken)
            check(False, "应当拒绝不完整的目录")
        except provision.ProvisionError as exc:
            check("requirements.txt" in str(exc), f"指出缺失的文件：{str(exc)[:60]}")

        print("\n[4] 源码多套一层目录时指出实际位置")
        wrapped = workspace / "wrapped"
        make_source(wrapped, nested="autopcr-main")
        try:
            await provision.ensure_source(wrapped)
            check(False, "应当拒绝并给出提示")
        except provision.ProvisionError as exc:
            check("autopcr-main" in str(exc), f"指出源码所在的下一层目录：{str(exc)[:70]}")

        print("\n[5] 位置落在插件目录内且名称不当时被拒绝")
        inside = provision.config.PROJECT_ROOT / "autopcr_source"
        try:
            provision.check_source_location(inside)
            check(False, "应当拒绝会被宿主框架扫描到的位置")
        except provision.ProvisionError as exc:
            check("插件目录" in str(exc), f"说明原因：{str(exc)[:50]}")
        provision.check_source_location(provision.config.PROJECT_ROOT / ".autopcr")
        check(True, "以点开头的位置被接受")
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
