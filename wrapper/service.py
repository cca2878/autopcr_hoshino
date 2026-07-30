"""wrapper 侧的调用处理。

接收兼容层发来的调用并分发到对应实现。事件处理在独立任务中进行，
因此一条耗时较长的命令不会阻塞其他命令，也不会阻塞该命令自身发起的回调。
"""
import logging
from typing import Any, Dict, Optional

from ..protocol import Peer
from .remote_event import CommandFinished, RemoteBotEvent

logger = logging.getLogger("autopcr_hoshino.wrapper.service")


class WrapperService:
    """把兼容层的调用转换为对命令实现的调用。"""

    def __init__(self):
        self._peer = None  # type: Optional[Peer]
        self._web_port = None  # type: Optional[int]

    def attach(self, peer: Peer) -> None:
        self._peer = peer
        if self._web_port is not None:
            peer.notify("report_web_port", port=self._web_port)

    def report_web_port(self, port: int) -> None:
        """记录网页端端口，并在连接可用时上报给兼容层。"""
        self._web_port = port
        if self._peer is not None:
            self._peer.notify("report_web_port", port=port)

    async def is_valid_qq(self, qq: str) -> bool:
        """询问兼容层，该号码是否仍在机器人所在的群内。

        该判定不属于任何一次消息事件，因此不携带会话编号。
        连接不可用时判定为无效：此时无法确认号码归属，放行会让任何人都能注册。
        """
        if self._peer is None:
            logger.warning("与兼容层的连接不可用，拒绝号码 %s 的注册", qq)
            return False
        invalid = await self._peer.call("filter_invalid_qq", session_id=None, qqs=[qq])
        return not invalid

    async def handle(self, method: str, params: Dict[str, Any]) -> Any:
        if method == "ping":
            return {"ready": True, "web_port": self._web_port}
        if method == "echo":
            # 用于验证链路连通性与大消息传输，不涉及 autopcr。
            return params.get("payload")
        if method == "dispatch":
            return await self._dispatch(params)
        raise ValueError(f"未知的方法：{method}")

    async def _dispatch(self, params: Dict[str, Any]) -> Optional[str]:
        from .commands import dispatch

        event = RemoteBotEvent(self._peer, params["event"])
        command = params["command"]
        try:
            await dispatch(command, event)
        except CommandFinished:
            # 命令已通过 finish 给出最终答复，属于正常结束。
            pass
        except Exception as exc:
            logger.exception("执行命令 %s 时出错", command)
            await event.send(f"执行失败：{exc}")
        return None
