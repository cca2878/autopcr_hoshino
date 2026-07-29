"""消息事件的拆解与会话登记。

宿主框架的前缀触发器在把控制权交给处理函数之前，会就地去掉消息中的命令前缀，
并在处理函数返回后还原。因此消息内容必须在处理函数内当场拆解，
不能先保存事件对象稍后再读——那时读到的将是包含前缀的原始消息。

拆解结果连同权限判定一并送往 wrapper。权限判定在此处一次求出，
使 wrapper 侧读取权限时无需往返。
"""
import asyncio
import itertools
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

_session_ids = itertools.count(1)


class Session:
    """一次事件处理期间的上下文，供 wrapper 的回调定位其所属事件。"""

    __slots__ = ("id", "bot", "event")

    def __init__(self, session_id: int, bot, event):
        self.id = session_id
        self.bot = bot
        self.event = event


#: 命令返回后会话的保留秒数。
#:
#: 命令可以留下后台协程继续工作——等待登录验证码就是如此，它最长会等待数分钟，
#: 期间需要通过会话把认证链接发给用户。因此会话不能在命令返回时立即回收。
SESSION_LINGER = 600.0

#: 会话表的容量上限。达到上限时回收最早的会话，避免异常情况下无限增长。
MAX_SESSIONS = 512


class SessionRegistry:
    """保存处理中的会话，并在命令返回一段时间后回收。"""

    def __init__(self, linger: float = SESSION_LINGER, capacity: int = MAX_SESSIONS):
        self._sessions = OrderedDict()  # type: OrderedDict
        self._linger = linger
        self._capacity = capacity

    def open(self, bot, event) -> Session:
        session = Session(next(_session_ids), bot, event)
        self._sessions[session.id] = session
        while len(self._sessions) > self._capacity:
            self._sessions.popitem(last=False)
        return session

    def close(self, session: Session) -> None:
        """安排回收。命令虽已返回，其后台协程仍可能需要该会话。"""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            self._sessions.pop(session.id, None)
            return
        loop.call_later(self._linger, self._sessions.pop, session.id, None)

    def get(self, session_id: int) -> Optional[Session]:
        return self._sessions.get(session_id)

    def __len__(self) -> int:
        return len(self._sessions)


def split_message(event) -> Tuple[List[str], str, List[str], List[str]]:
    """把消息段拆成记号列表、原始文本、图片地址与被提及的号码。"""
    mentioned = []  # type: List[str]
    tokens = []  # type: List[str]
    images = []  # type: List[str]
    raw = ""

    for segment in event.message:
        if segment.type == "at" and segment.data.get("qq") != "all":
            mentioned.append(str(segment.data["qq"]))
        elif segment.type == "text":
            text = segment.data["text"]
            raw += text
            tokens += text.split()
        elif segment.type == "image":
            images.append(segment.data["url"])

    return tokens, raw, images, mentioned


def build_payload(
    session: Session, command: str, web_address: str
) -> Dict[str, Any]:
    """构造送往 wrapper 的事件数据。"""
    from hoshino import priv

    event = session.event
    tokens, raw, images, mentioned = split_message(event)

    return {
        "session_id": session.id,
        "command": command,
        "message": tokens,
        "message_raw": raw,
        "images": images,
        "at": mentioned,
        "user_id": str(event.user_id),
        "group_id": str(getattr(event, "group_id", "") or ""),
        "is_admin": priv.check_priv(event, priv.ADMIN),
        "is_super_admin": priv.check_priv(event, priv.SU),
        "web_address": web_address,
    }
