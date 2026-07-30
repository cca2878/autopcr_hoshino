"""跨环境通信测试。

在装有宿主框架依赖的解释器（Python 3.8）中运行，由它拉起装有 autopcr 依赖的
wrapper 子进程（Python 3.10），走完整的真实代码路径验证：

* 子进程能被拉起，连接与双向认证成立。
* 请求与响应能跨解释器版本往返。
* 兆字节量级的消息能完整传输。
* 事件分发能触达命令实现，且命令发出的即发即忘消息能回到本端。
* 多条命令可以并发处理。
* 密钥不匹配的连接会被拒绝。
* 子进程异常退出后被重新拉起，恢复后服务可用。

本测试不需要 autopcr 就绪，因此 wrapper 以关闭 autopcr 的方式启动。
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from autopcr_hoshino.hbot.supervisor import Supervisor  # noqa: E402
from autopcr_hoshino.protocol import perform_handshake  # noqa: E402
from autopcr_hoshino.protocol.handshake import AuthenticationError  # noqa: E402

WEB_ADDRESS = "http://example.invalid/daily/"

received = []
failures = []


def check(condition: bool, description: str) -> None:
    if condition:
        print(f"  [通过] {description}")
    else:
        failures.append(description)
        print(f"  [失败] {description}")


async def handle_callback(method, params):
    """兼容层侧的回调处理，记录 wrapper 发来的每一次调用。"""
    received.append((method, params))
    if method in ("send", "finish", "report_web_port"):
        return None
    if method == "filter_invalid_qq":
        return []
    if method == "get_group_member_list":
        return [["10001", "甲"], ["10002", "乙"]]
    raise ValueError(f"未预期的回调：{method}")


def make_event(session_id, command, message=None):
    return {
        "session_id": session_id,
        "command": command,
        "message": message or [],
        "message_raw": "",
        "images": [],
        "at": [],
        "user_id": "10001",
        "group_id": "20001",
        "is_admin": True,
        "is_super_admin": False,
        "web_address": WEB_ADDRESS,
    }


async def run_checks(supervisor):
    print("\n[2] 请求与响应")
    pong = await supervisor.call("ping")
    check(pong.get("ready") is True, "ping 返回就绪状态")

    print("\n[3] 大消息传输")
    payload = "X" * 3_000_000
    echoed = await supervisor.call("echo", payload=payload)
    check(echoed == payload, "3 MB 消息原样返回")

    print("\n[4] 非 ASCII 内容")
    echoed = await supervisor.call("echo", payload="日常清理完毕 ✓ [CQ:image]")
    check(echoed == "日常清理完毕 ✓ [CQ:image]", "中文与特殊字符原样返回")

    print("\n[5] 事件分发与即发即忘回调")
    received.clear()
    await supervisor.call(
        "dispatch", command="#配置日常", event=make_event(1, "#配置日常")
    )
    await asyncio.sleep(0.2)
    finish_calls = [p for m, p in received if m == "finish"]
    check(len(finish_calls) == 1, "命令实现发出了一条最终答复")
    check(
        finish_calls and finish_calls[0].get("msg") == WEB_ADDRESS + "login",
        "答复内容为网页端登录地址",
    )
    check(
        finish_calls and finish_calls[0].get("session_id") == 1,
        "回调携带正确的会话编号",
    )

    print("\n[6] 并发处理")
    received.clear()
    await asyncio.gather(
        *[
            supervisor.call(
                "dispatch", command="#配置日常", event=make_event(i, "#配置日常")
            )
            for i in range(2, 12)
        ]
    )
    await asyncio.sleep(0.2)
    sessions = sorted(p["session_id"] for m, p in received if m == "finish")
    check(sessions == list(range(2, 12)), "十条并发命令各自返回且会话未串扰")

    print("\n[7] 未登记的命令")
    try:
        await supervisor.call(
            "dispatch", command="#不存在的命令", event=make_event(99, "#不存在的命令")
        )
        errors = [p for m, p in received if m == "send" and "执行失败" in p.get("msg", "")]
        check(bool(errors), "未登记命令被报告为执行失败")
    except Exception as exc:
        check(False, f"未登记命令不应导致调用抛出：{exc!r}")


async def check_restart(supervisor):
    """子进程异常退出后应被重新拉起，且恢复后服务可用。"""
    supervisor._process.kill()
    for _ in range(50):
        if not supervisor.alive:
            break
        await asyncio.sleep(0.1)
    check(not supervisor.alive, "子进程被杀后连接随之断开")

    check(await supervisor.wait_ready(90), "wrapper 已被重新拉起")
    pong = await supervisor.call("ping")
    check(pong.get("ready") is True, "重启后服务恢复可用")


async def check_authentication_rejected(port):
    """使用错误密钥连接，应当被拒绝。"""
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        await perform_handshake(reader, writer, "0" * 64)
    except (AuthenticationError, asyncio.IncompleteReadError):
        check(True, "错误密钥的连接被拒绝")
        return
    finally:
        writer.close()
    check(False, "错误密钥的连接被拒绝")


async def main():
    os.environ["AUTOPCR_HOSHINO_ENABLE_AUTOPCR"] = "false"

    print("[1] 拉起 wrapper 子进程并完成认证")
    print(f"  兼容层解释器 {sys.version.split()[0]}")
    supervisor = Supervisor(handle_callback)
    await supervisor.start()
    ready = await supervisor.wait_ready(60)
    check(ready, "wrapper 在超时前完成连接与认证")
    if not ready:
        return 1

    try:
        await run_checks(supervisor)

        print("\n[8] 认证拒绝")
        port = supervisor._server.sockets[0].getsockname()[1]
        await check_authentication_rejected(port)

        print("\n[9] 子进程异常退出后自动重启")
        await check_restart(supervisor)
    finally:
        await supervisor.stop()

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
