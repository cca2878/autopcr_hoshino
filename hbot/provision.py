"""autopcr 源码与运行环境的自动准备。

未显式指定 autopcr 位置时，本模块负责取得源码、创建运行环境并安装依赖，
使部署只需放好插件目录即可。已显式指定位置时不作任何改动，由使用者自行管理。

准备过程涉及网络下载，耗时可达数分钟，因此在后台进行，不阻塞宿主框架启动。
期间收到的命令会得到"服务尚未就绪"的提示。

数据安全：账号配置、母数据与运行结果位于源码目录下的 ``cache`` 与 ``result``，
这两个目录不受版本控制。更新源码只做快进式合并，且在存在本地改动时跳过，
不执行任何清理操作。
"""
import asyncio
import hashlib
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from . import config

logger = logging.getLogger("autopcr_hoshino.provision")


class ProvisionError(Exception):
    """无法完成准备工作。"""


async def _run(command: List[str], cwd: Optional[Path] = None, timeout: float = 1800.0):
    """执行外部命令，返回退出码与合并后的输出。"""
    logger.info("执行：%s", " ".join(command))
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout)
    except asyncio.TimeoutError as exc:
        process.kill()
        raise ProvisionError("命令超时：{}".format(" ".join(command))) from exc
    output = stdout.decode("utf-8", "replace").strip()
    return process.returncode, output


async def _run_checked(
    command: List[str], cwd: Optional[Path] = None, timeout: float = 1800.0
) -> str:
    code, output = await _run(command, cwd, timeout)
    if code != 0:
        raise ProvisionError(
            "命令失败（退出码 {}）：{}\n{}".format(code, " ".join(command), output[-2000:])
        )
    return output


def find_executable(*names: str) -> Optional[str]:
    """在可执行文件搜索路径与常见安装位置中查找程序。"""
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    # uv 的默认安装位置不一定在搜索路径中。
    for name in names:
        candidate = Path.home() / ".local" / "bin" / name
        if candidate.exists():
            return str(candidate)
    return None


# ---------------------------------------------------------------- 源码


def check_source_location(root: Path) -> None:
    """确认源码位置不会被宿主框架当作插件加载。

    宿主框架会导入插件目录下的每一个子目录，而 autopcr 仓库根目录带有 ``__init__.py``。
    若源码落在本项目目录内且目录名不以点或下划线开头，它将被宿主框架在其自身的解释器中
    导入，随即因缺少依赖而失败。以点或下划线开头的名字会被其模块扫描跳过。
    """
    root = root.resolve()
    project = config.PROJECT_ROOT.resolve()
    try:
        relative = root.relative_to(project)
    except ValueError:
        return
    first = relative.parts[0] if relative.parts else ""
    if first and not first.startswith((".", "_")):
        raise ProvisionError(
            f"源码位置 {root} 在插件目录内且名称不以点或下划线开头，"
            "会被宿主框架误当作插件加载。请改用以点开头的目录名，"
            "或把它放到插件目录之外。"
        )


#: 判定一份目录是否为可用的 autopcr 源码所依据的文件。
SOURCE_MARKERS = (
    Path("autopcr") / "__init__.py",
    Path("autopcr") / "http_server" / "httpserver.py",
    Path("autopcr") / "module" / "accountmgr.py",
    Path("requirements.txt"),
)


def missing_markers(root: Path) -> List[str]:
    """列出使该目录不成为可用 autopcr 源码的缺失文件。"""
    return [str(marker) for marker in SOURCE_MARKERS if not (root / marker).exists()]


def is_valid_source(root: Path) -> bool:
    """该目录是否为一份可用的 autopcr 源码。"""
    return root.is_dir() and not missing_markers(root)


def _describe_invalid_source(root: Path) -> str:
    """说明目录为何不可用，并在可能时指出源码的实际位置。

    从压缩包解压得到的源码常多套一层目录，这种情形单看缺失文件清单不易察觉。
    """
    detail = "目录 {} 中缺少 {}".format(root, "、".join(missing_markers(root)))
    try:
        nested = [child for child in root.iterdir() if is_valid_source(child)]
    except OSError:
        nested = []
    if nested:
        return (
            f"{detail}。源码似位于其下一层的 {nested[0].name}，"
            "请把该目录的内容上移，或直接指向它。"
        )
    return (
        f"{detail}。若网络受限无法自动取得，可自行下载 autopcr 源码解压至该目录；"
        "其中应直接包含 autopcr 包与 requirements.txt。"
    )


async def ensure_source(root: Path) -> Path:
    """取得或更新 autopcr 源码，返回其所在目录。

    目录中已有可用源码时直接使用，不要求它由 git 取得——网络受限时可自行下载放置，
    此种情形下无法自动更新。目录为空时才会尝试克隆。
    """
    check_source_location(root)

    if is_valid_source(root):
        if not (root / ".git").exists():
            logger.info("使用已有的 autopcr 源码 %s（非 git 仓库，不做更新）", root)
            return root
        if not config.auto_update():
            logger.info("autopcr 源码已存在，未启用自动更新")
            return root
        return await _update_source(root)

    if root.exists() and any(root.iterdir()):
        raise ProvisionError(_describe_invalid_source(root))

    git = find_executable("git")
    if git is None:
        raise ProvisionError(
            "未找到 git，无法自动取得 autopcr 源码；"
            f"可自行下载源码解压至 {root} 后重启"
        )
    root.parent.mkdir(parents=True, exist_ok=True)
    command = [git, "clone", "--depth", "1"]
    if config.autopcr_ref():
        command += ["--branch", config.autopcr_ref()]
    command += [config.autopcr_repo(), str(root)]
    await _run_checked(command)
    if not is_valid_source(root):
        raise ProvisionError(_describe_invalid_source(root))
    logger.info("已取得 autopcr 源码至 %s", root)
    return root


async def _update_source(root: Path) -> Path:
    """把已有的 git 工作树快进到远端最新提交。"""
    git = find_executable("git")
    if git is None:
        logger.warning("未找到 git，跳过 autopcr 源码更新")
        return root

    # 存在本地改动时不动源码：使用者可能正在调试。
    status = await _run_checked([git, "status", "--porcelain", "--untracked-files=no"], root)
    if status:
        logger.warning("autopcr 源码存在本地改动，跳过更新")
        return root

    await _run_checked([git, "fetch", "--depth", "1", "origin"], root)
    ref = config.autopcr_ref() or "HEAD"
    # 只做快进：不改写历史，也不触碰未跟踪的账号数据。
    code, output = await _run([git, "merge", "--ff-only", "FETCH_HEAD"], root)
    if code != 0:
        logger.warning("autopcr 源码无法快进更新至 %s，保持当前版本：%s", ref, output[-500:])
    else:
        logger.info("autopcr 源码已更新")
    return root


# ---------------------------------------------------------------- 运行环境


def _requirements_stamp(source: Path) -> Path:
    return source / ".autopcr_hoshino_requirements"


def _requirements_digest(requirements: Path) -> str:
    return hashlib.sha256(requirements.read_bytes()).hexdigest()


async def ensure_venv(source: Path, venv: Path) -> str:
    """创建运行环境并安装依赖，返回其解释器路径。"""
    python = venv / ("Scripts" if os.name == "nt" else "bin") / (
        "python.exe" if os.name == "nt" else "python"
    )
    requirements = source / "requirements.txt"
    if not requirements.exists():
        raise ProvisionError(f"未找到 {requirements}")

    uv = find_executable("uv")

    if not python.exists():
        if uv is not None:
            await _run_checked([uv, "venv", "--python", config.autopcr_python_version(), str(venv)])
        else:
            base = find_executable(
                "python" + config.autopcr_python_version(), "python3", "python"
            )
            if base is None:
                raise ProvisionError(
                    f"未找到 uv，也未找到 Python {config.autopcr_python_version()} 解释器，"
                    "无法创建运行环境"
                )
            logger.warning("未找到 uv，改用 %s 创建运行环境", base)
            await _run_checked([base, "-m", "venv", str(venv)])
        logger.info("已创建运行环境 %s", venv)

    # 依赖清单未变时跳过安装：一次完整安装耗时可达数分钟。
    digest = _requirements_digest(requirements)
    stamp = _requirements_stamp(source)
    if stamp.exists() and stamp.read_text().strip() == digest:
        logger.info("依赖清单未变，跳过安装")
        return str(python)

    if uv is not None:
        await _run_checked(
            [uv, "pip", "install", "--python", str(python), "-r", str(requirements)]
        )
    else:
        await _run_checked([str(python), "-m", "pip", "install", "-r", str(requirements)])
    stamp.write_text(digest)
    logger.info("依赖安装完成")
    return str(python)


async def ensure_frontend(source: Path, python: str) -> None:
    """取得网页端前端资源。缺失时页面无法打开，但接口仍可用。"""
    index = source / "autopcr" / "http_server" / "ClientApp" / "index.html"
    if index.exists():
        return
    script = source / "_download_web.py"
    if not script.exists():
        logger.warning("未找到 %s，跳过前端资源准备", script)
        return
    code, output = await _run([python, str(script)], source, timeout=600.0)
    if code != 0:
        logger.warning("前端资源下载失败，网页端页面将不可用：%s", output[-500:])
    else:
        logger.info("前端资源准备完成")


# ---------------------------------------------------------------- 入口


async def provision() -> Tuple[str, str]:
    """准备源码与运行环境，返回源码目录与解释器路径。"""
    root = Path(config.managed_root())
    source = await ensure_source(root)
    python = await ensure_venv(source, Path(config.managed_venv()))
    await ensure_frontend(source, python)
    return str(source), python


def is_managed() -> bool:
    """是否由本项目负责准备。

    显式指定了 autopcr 位置即视为使用者自行管理，此时不做任何准备工作。
    """
    if not config.auto_provision():
        return False
    return not config.autopcr_root()


def describe_requirements() -> str:
    """给出自动准备所需的外部程序状况，供排障使用。"""
    parts = []
    for name in ("git", "uv"):
        found = find_executable(name)
        parts.append("{}={}".format(name, found or "缺失"))
    parts.append(f"python={sys.version.split()[0]}")
    return "，".join(parts)
