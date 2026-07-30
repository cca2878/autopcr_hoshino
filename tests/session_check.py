"""会话保留测试。

命令返回后，它留下的后台协程仍可能需要通过会话发送消息——等待登录验证码即是如此。
本测试验证会话在命令返回后仍可用，并在保留期结束后被回收。
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from autopcr_hoshino.hbot.callbacks import CallbackHandler  # noqa: E402
from autopcr_hoshino.hbot.event import SessionRegistry  # noqa: E402

failures = []


def check(condition, description):
    if condition:
        print(f"  [通过] {description}")
    else:
        failures.append(description)
        print(f"  [失败] {description}")


class FakeEvent:
    message_id = 1
    user_id = 10001
    group_id = 20001
    message = []


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send(self, event, message):
        self.sent.append(message)


async def main():
    print("[1] 命令返回后会话仍然可用")
    registry = SessionRegistry(linger=1.0, capacity=4)
    bot = FakeBot()
    handler = CallbackHandler(None, registry, lambda: None)

    session = registry.open(bot, FakeEvent())
    registry.close(session)  # 命令已返回，安排回收

    await handler("send", {"session_id": session.id, "msg": "验证码链接"})
    check(bot.sent and "验证码链接" in bot.sent[-1], "回收安排后仍可通过会话发送消息")

    print("\n[2] 保留期结束后会话被回收")
    await asyncio.sleep(1.3)
    check(registry.get(session.id) is None, "保留期结束后会话已移除")
    try:
        await handler("send", {"session_id": session.id, "msg": "过期"})
        check(False, "对已回收的会话发送消息应当报错")
    except ValueError as exc:
        check("会话已结束" in str(exc), f"对已回收的会话给出明确错误：{exc}")

    print("\n[3] 容量上限")
    registry = SessionRegistry(linger=600.0, capacity=4)
    ids = [registry.open(bot, FakeEvent()).id for _ in range(10)]
    check(len(registry) == 4, f"会话数量不超过上限，实为 {len(registry)}")
    check(registry.get(ids[-1]) is not None, "最新的会话被保留")
    check(registry.get(ids[0]) is None, "最早的会话已被回收")

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
