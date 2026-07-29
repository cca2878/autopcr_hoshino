"""跨进程的机器人事件对象。

autopcr 原有的命令实现依赖一个抽象事件对象来读取消息内容、查询权限、回发消息。
本模块提供该抽象的跨进程实现：消息内容与权限判定在事件产生时由兼容层一次性求出并随事件下发，
读取这些内容不产生任何往返；只有需要宿主框架当场执行的动作才发起调用。

方法划分如下：

* 本地读取：``target_qq`` ``send_qq`` ``group_id`` ``message`` ``message_raw``
  ``image`` ``is_admin`` ``is_super_admin``
* 即发即忘：``send`` ``finish``
* 需要返回值：``get_group_member_list`` ``call_action`` ``upload_file``
"""
import base64
from typing import Any, Dict, List, Optional, Tuple


class CommandFinished(Exception):
    """命令已给出最终答复，应当立即停止后续处理。

    宿主框架的 ``finish`` 通过抛出异常中断处理链，跨进程后该异常无法自动跨越进程边界，
    因此由本端在发出消息后主动抛出，并在命令分发的最外层捕获。
    缺少这一步会导致本应终止的分支继续执行。
    """


class RemoteBotEvent:
    """一次群消息事件在 wrapper 侧的视图。"""

    def __init__(self, peer, data: Dict[str, Any]):
        self._peer = peer
        self._session_id = data["session_id"]
        self._user_id = str(data.get("user_id", ""))
        self._group_id = str(data.get("group_id", ""))
        self._at = [str(x) for x in data.get("at", [])]
        self._message = list(data.get("message", []))
        self._message_raw = data.get("message_raw", "")
        self._images = list(data.get("images", []))
        self._is_admin = bool(data.get("is_admin", False))
        self._is_super_admin = bool(data.get("is_super_admin", False))
        #: 网页端对外地址，形如 ``http://example.com/daily/``。
        #: 该地址取决于宿主框架的部署方式，由兼容层随事件下发。
        self.web_address = data.get("web_address", "")

    # ---------------------------------------------------------------- 本地读取

    async def target_qq(self) -> str:
        """被操作账号所属的号码，未指定时为发送者本人。"""
        if len(self._at) > 1:
            await self.finish("只能指定一个用户")
        return self._at[0] if self._at else self._user_id

    async def send_qq(self) -> str:
        return self._user_id

    async def group_id(self) -> str:
        return self._group_id

    async def message(self) -> List[str]:
        """剩余参数记号。

        返回的是同一个列表对象而非副本：命令解析过程通过就地删除元素来消费参数，
        逐层解析器据此判断哪些记号尚未被处理。
        """
        return self._message

    async def message_raw(self) -> str:
        return self._message_raw

    async def image(self) -> List[str]:
        return self._images

    async def is_admin(self) -> bool:
        return self._is_admin

    async def is_super_admin(self) -> bool:
        return self._is_super_admin

    # ---------------------------------------------------------------- 即发即忘

    async def send(self, msg: str) -> None:
        self._peer.notify("send", session_id=self._session_id, msg=msg)

    async def finish(self, msg: str) -> None:
        """发出最终答复并终止本次命令。"""
        self._peer.notify("finish", session_id=self._session_id, msg=msg)
        raise CommandFinished(msg)

    # ---------------------------------------------------------------- 需要返回值

    async def get_group_member_list(self) -> List[Tuple[str, str]]:
        """本群成员的号码与昵称，按昵称排序。"""
        result = await self._peer.call(
            "get_group_member_list", session_id=self._session_id
        )
        return [(str(qq), str(name)) for qq, name in result]

    async def call_action(self, action: str, **kwargs) -> Dict[str, Any]:
        """直接调用宿主框架的机器人接口。"""
        return await self._peer.call(
            "call_action", session_id=self._session_id, action=action, params=kwargs
        )

    async def filter_invalid_qq(self, qqs: List[str]) -> List[str]:
        """从给定号码中挑出已不在任何启用群内的那些。

        一次调用完成全部判定：宿主框架需要逐群拉取成员名单，
        逐个号码询问会导致成员名单被反复拉取。
        """
        result = await self._peer.call(
            "filter_invalid_qq", session_id=self._session_id, qqs=list(qqs)
        )
        return [str(qq) for qq in result]

    async def upload_file(
        self, data: bytes, filename: str, folder_name: Optional[str] = None
    ) -> None:
        """把文件上传到本群。

        文件内容经 base64 编码传给兼容层，由其写入宿主框架的资源目录后再发起上传。
        资源目录与其对外地址属于宿主框架的配置，wrapper 无从得知，因此整个落盘与
        上传流程都在兼容层完成。
        """
        await self._peer.call(
            "upload_file",
            session_id=self._session_id,
            filename=filename,
            folder_name=folder_name,
            content=base64.b64encode(data).decode("ascii"),
        )
