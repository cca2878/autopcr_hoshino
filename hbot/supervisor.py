"""wrapper 子进程的生命周期管理与通信端点。

兼容层先在回环地址上监听一个由系统分配的端口，再启动 wrapper 子进程并通过环境变量
告知端口与共享密钥，由子进程反向连接回来。这样端口无需协商、无需写入文件，
也不占用子进程的标准输出——wrapper 及其依赖可以自由地向标准输出与标准错误打印日志。

子进程退出后会自动重启。重启期间发起的调用将立即失败，由命令处理器给出提示。
"""
import asyncio
import ctypes
import logging
import os
import signal
import sys
from typing import Any, Dict, Optional

from ..protocol import Peer, generate_key, perform_handshake
from ..protocol.peer import ConnectionClosed
from . import config

logger = logging.getLogger("autopcr_hoshino.supervisor")

#: Linux 的 ``prctl`` 操作码，用于设置父进程终止时子进程收到的信号。
_PR_SET_PDEATHSIG = 1


def _die_with_parent() -> None:
    """请求内核在父进程终止时一并终止本进程。

    正常关闭由宿主框架的关闭钩子处理；此机制覆盖宿主进程被强制终止的情形，
    避免留下仍在运行的 wrapper 与其占用的端口。仅 Linux 提供该能力。
    """
    if not sys.platform.startswith("linux"):
        return
    try:
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(_PR_SET_PDEATHSIG, signal.SIGTERM)
    except OSError:
        pass


class WrapperUnavailable(Exception):
    """wrapper 尚未就绪或已断开。"""


class Supervisor:
    """维护与 wrapper 的连接，并在其退出后重新拉起。"""

    def __init__(self, handler, provisioner=None):
        self._handler = handler
        self._provisioner = provisioner
        self._key = generate_key()
        self._server = None
        self._peer = None  # type: Optional[Peer]
        self._process = None
        self._web_port = None  # type: Optional[int]
        self._ready = asyncio.Event()
        self._stopping = False
        self._supervise_task = None
        #: 自动准备得到的源码目录与解释器，未启用自动准备时为 ``None``。
        self._provisioned = None  # type: Optional[tuple]
        #: 准备失败的原因，供命令处理器向用户说明。
        self._provision_error = None  # type: Optional[str]

    # ---------------------------------------------------------------- 对外接口

    @property
    def web_port(self) -> Optional[int]:
        """wrapper 网页端实际监听的端口，未就绪时为 ``None``。"""
        return self._web_port

    @property
    def alive(self) -> bool:
        return self._peer is not None

    def set_web_port(self, port: int) -> None:
        self._web_port = port
        logger.info("wrapper 网页端监听于 127.0.0.1:%s", port)

    async def call(self, method: str, **params) -> Any:
        """向 wrapper 发起调用，未就绪时抛出 :class:`WrapperUnavailable`。"""
        peer = self._peer
        if peer is None:
            if self._provision_error is not None:
                raise WrapperUnavailable(
                    f"autopcr 环境准备失败：{self._provision_error}"
                )
            raise WrapperUnavailable("autopcr 服务尚未就绪")
        try:
            return await peer.call(method, **params)
        except ConnectionClosed as exc:
            raise WrapperUnavailable("autopcr 服务连接已断开") from exc

    async def wait_ready(self, timeout: Optional[float] = None) -> bool:
        """等待 wrapper 完成连接与认证。"""
        if timeout is None:
            timeout = config.STARTUP_TIMEOUT
        try:
            await asyncio.wait_for(self._ready.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def start(self) -> None:
        """开始监听并拉起 wrapper。"""
        self._server = await asyncio.start_server(
            self._on_connection, "127.0.0.1", 0
        )
        port = self._server.sockets[0].getsockname()[1]
        logger.info("等待 wrapper 连接于 127.0.0.1:%s", port)
        self._supervise_task = asyncio.ensure_future(self._supervise(port))

    async def stop(self) -> None:
        """停止监督并终止子进程。"""
        self._stopping = True
        if self._supervise_task is not None:
            self._supervise_task.cancel()
        if self._process is not None and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), 10)
            except asyncio.TimeoutError:
                self._process.kill()
        if self._server is not None:
            self._server.close()

    # ---------------------------------------------------------------- 内部实现

    async def _on_connection(self, reader, writer) -> None:
        address = writer.get_extra_info("peername")
        try:
            await perform_handshake(reader, writer, self._key)
        except Exception as exc:
            logger.warning("来自 %s 的连接认证失败：%s", address, exc)
            writer.close()
            return

        logger.info("wrapper 已连接并通过认证")
        peer = Peer(reader, writer, self._handler, name="wrapper")
        self._peer = peer
        self._ready.set()
        try:
            await peer.run()
        finally:
            if self._peer is peer:
                self._peer = None
                self._web_port = None
                self._ready.clear()
            logger.info("与 wrapper 的连接已结束")

    def _child_environment(self, port: int) -> Dict[str, str]:
        env = dict(os.environ)
        env["AUTOPCR_HOSHINO_RPC_PORT"] = str(port)
        env["AUTOPCR_HOSHINO_RPC_KEY"] = self._key
        # 共享密钥经环境变量传递。命令行参数在 /proc/<pid>/cmdline 中对本机所有用户可读，
        # 环境变量所在的 /proc/<pid>/environ 仅进程属主可读。
        # 搜索路径指向项目所在目录的上一级，使 wrapper 能以本项目的包名被导入，
        # 从而与在宿主框架中被加载时使用同一套相对导入。
        search_path = [str(config.PROJECT_ROOT.parent)]
        autopcr_root = self._autopcr_root()
        if autopcr_root:
            search_path.append(autopcr_root)
        existing = env.get("PYTHONPATH")
        if existing:
            search_path.append(existing)
        env["PYTHONPATH"] = os.pathsep.join(search_path)
        return env

    def _autopcr_root(self) -> str:
        """autopcr 源码目录。显式配置优先于自动准备的结果。"""
        configured = config.autopcr_root()
        if configured:
            return configured
        return self._provisioned[0] if self._provisioned else ""

    def _python(self) -> str:
        """运行 wrapper 的解释器。自动准备的结果仅在未显式配置时生效。"""
        if self._provisioned and not os.getenv("AUTOPCR_HOSHINO_PYTHON", "").strip():
            return self._provisioned[1]
        return config.wrapper_python()

    async def _provision(self) -> bool:
        """在拉起 wrapper 之前准备源码与运行环境。"""
        if self._provisioner is None:
            return True
        try:
            self._provisioned = await self._provisioner()
            self._provision_error = None
            logger.info("autopcr 环境已就绪：%s", self._provisioned[0])
            return True
        except Exception as exc:
            self._provision_error = str(exc)
            logger.error("autopcr 环境准备失败：%s", exc)
            return False

    async def _supervise(self, port: int) -> None:
        module = f"{config.PACKAGE_NAME}.wrapper"
        # 连续失败时逐次延长重启间隔，避免配置错误导致进程被反复拉起。
        # 一旦某次运行持续足够长，视为已恢复，间隔重置。
        delay = config.RESTART_DELAY

        while not self._stopping:
            if await self._provision():
                break
            logger.error("%s 秒后重试准备 autopcr 环境", delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, config.MAX_RESTART_DELAY)
        delay = config.RESTART_DELAY

        while not self._stopping:
            python = self._python()
            logger.info("启动 wrapper：%s -m %s", python, module)
            started_at = asyncio.get_event_loop().time()
            try:
                self._process = await asyncio.create_subprocess_exec(
                    python,
                    "-m",
                    module,
                    cwd=str(config.PROJECT_ROOT.parent),
                    env=self._child_environment(port),
                    # 不捕获标准流：子进程日志直接进入宿主的控制台或日志文件。
                    stdout=None,
                    stderr=None,
                    preexec_fn=_die_with_parent,
                )
            except OSError as exc:
                logger.error("无法启动 wrapper：%s", exc)
                await asyncio.sleep(delay)
                delay = min(delay * 2, config.MAX_RESTART_DELAY)
                continue

            returncode = await self._process.wait()
            if self._stopping:
                return

            if asyncio.get_event_loop().time() - started_at >= config.HEALTHY_UPTIME:
                delay = config.RESTART_DELAY
            logger.error("wrapper 已退出（返回码 %s），%s 秒后重启", returncode, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, config.MAX_RESTART_DELAY)
