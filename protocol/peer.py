"""对等双向 RPC 端点。

连接建立后两端完全对等：都可以发起调用，也都要处理对端发来的调用。
兼容层需要把群消息事件推给 wrapper，wrapper 需要反过来请求发消息、查权限、传文件，
两个方向同时进行且互不阻塞。

并发模型基于单线程事件循环：

* 一个读循环负责收帧，收到请求即 ``create_task`` 交给处理器，慢请求不会挡住后续帧。
* 一个写协程从队列取帧发送，因此任意多个协程可以并发调用 :meth:`Peer.notify`
  与 :meth:`Peer.call` 而无需加锁，背压由队列到写协程这条单通路自然形成。

调用语义分两种：

* :meth:`Peer.call` 需要返回值，携带自增的请求编号，响应按编号派发。
* :meth:`Peer.notify` 不需要返回值，发出即返回。发送群消息一类的操作用它，
  因为宿主框架本身就是即发即忘的，等待响应只会平白增加一个往返。

本模块必须同时运行于 Python 3.8 与 3.10，不使用任何高于 3.8 的语法。
"""
import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from . import framing
from .framing import ProtocolError

logger = logging.getLogger(__name__)

#: 单次 :meth:`Peer.call` 的默认超时秒数。清日常可能耗时数分钟，
#: 因此默认值取得较宽，需要更严格约束的调用应显式传入。
DEFAULT_CALL_TIMEOUT = 600.0

Handler = Callable[[str, Dict[str, Any]], Awaitable[Any]]


class RemoteError(Exception):
    """对端处理调用时抛出的异常。

    两端不共享自定义异常类型，因此只携带类型名与消息文本。
    """

    def __init__(self, type_name: str, message: str):
        super().__init__(f"{type_name}: {message}")
        self.type_name = type_name
        self.message = message


class ConnectionClosed(Exception):
    """连接已断开，调用无法完成。"""


class Peer:
    """一条已认证连接上的 RPC 端点。

    必须在事件循环内构造。生命周期由 :meth:`run` 界定，该协程返回即表示连接结束。
    """

    def __init__(self, reader, writer, handler: Handler, name: str = "peer"):
        self._reader = reader
        self._writer = writer
        self._handler = handler
        self._name = name
        self._pending = {}  # type: Dict[int, asyncio.Future]
        self._next_id = 0
        self._outbox = asyncio.Queue()  # type: asyncio.Queue
        self._closed = False
        self._tasks = set()

    # ---------------------------------------------------------------- 生命周期

    async def run(self) -> None:
        """驱动收发直到连接结束。正常断开不抛异常，协议错误会向上传播。"""
        writer_task = asyncio.ensure_future(self._write_loop())
        try:
            await self._read_loop()
        finally:
            self._closed = True
            writer_task.cancel()
            for task in list(self._tasks):
                task.cancel()
            self._abort_pending(ConnectionClosed(f"connection to {self._name} closed"))
            try:
                self._writer.close()
            except Exception:
                pass

    def _abort_pending(self, error: Exception) -> None:
        pending = self._pending
        self._pending = {}
        for future in pending.values():
            if not future.done():
                future.set_exception(error)

    async def _read_loop(self) -> None:
        while True:
            try:
                message = await framing.read(self._reader)
            except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
                logger.info("连接已由 %s 关闭", self._name)
                return
            if "method" in message:
                task = asyncio.ensure_future(self._dispatch(message))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
            else:
                self._resolve(message)

    async def _write_loop(self) -> None:
        while True:
            frame = await self._outbox.get()
            self._writer.write(frame)
            try:
                await self._writer.drain()
            except (ConnectionResetError, BrokenPipeError):
                logger.info("向 %s 写入失败，连接已断开", self._name)
                return

    # ---------------------------------------------------------------- 收到的消息

    def _resolve(self, message: dict) -> None:
        future = self._pending.pop(message.get("id"), None)
        if future is None or future.done():
            return
        error = message.get("error")
        if error:
            future.set_exception(
                RemoteError(error.get("type", "Error"), error.get("message", ""))
            )
        else:
            future.set_result(message.get("result"))

    async def _dispatch(self, message: dict) -> None:
        method = message.get("method")
        params = message.get("params") or {}
        request_id = message.get("id")
        result = None
        error = None
        try:
            result = await self._handler(method, params)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("处理来自 %s 的 %s 调用时出错", self._name, method)
            error = {"type": type(exc).__name__, "message": str(exc)}
        if request_id is not None:
            self._send({"id": request_id, "result": result, "error": error})

    # ---------------------------------------------------------------- 发出的消息

    def _send(self, message: dict) -> None:
        if self._closed:
            logger.warning("连接已关闭，丢弃发往 %s 的消息 %r", self._name, message.get("method"))
            return
        try:
            self._outbox.put_nowait(framing.encode(message))
        except ProtocolError:
            logger.exception("消息过大，无法发送")
            raise

    async def call(
        self, method: str, timeout: Optional[float] = DEFAULT_CALL_TIMEOUT, **params
    ) -> Any:
        """调用对端方法并等待返回值。

        :raises ConnectionClosed: 连接已断开或在等待期间断开。
        :raises RemoteError: 对端处理时抛出了异常。
        :raises asyncio.TimeoutError: 超过 ``timeout`` 秒仍未收到响应。
        """
        if self._closed:
            raise ConnectionClosed(f"connection to {self._name} is closed")
        self._next_id += 1
        request_id = self._next_id
        future = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future
        self._send({"id": request_id, "method": method, "params": params})
        try:
            if timeout is None:
                return await future
            return await asyncio.wait_for(future, timeout)
        finally:
            self._pending.pop(request_id, None)

    def notify(self, method: str, **params) -> None:
        """调用对端方法且不等待返回值。"""
        self._send({"id": None, "method": method, "params": params})
