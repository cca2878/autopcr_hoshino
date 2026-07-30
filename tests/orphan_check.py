"""孤儿进程测试。

宿主进程被强制终止时不会执行任何清理逻辑，wrapper 若继续运行便会占住端口
并持续访问游戏接口。本测试验证内核层面的兜底机制生效：

* 强制终止宿主进程后，wrapper 随之退出。

该机制依赖 Linux 的父进程终止信号，在其他系统上本测试跳过。
"""
import os
import signal
import subprocess
import sys
import tempfile
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: 宿主进程的源码。它拉起 wrapper 并报出其进程号，随后等待被强制终止。
#: 运行时写入临时目录，作为子进程启动，因此不作为独立文件进入版本控制。
HOST_SOURCE = """
import asyncio
import os
import sys

sys.path.insert(0, os.environ["AUTOPCR_HOSHINO_TEST_SYSPATH"])

from autopcr_hoshino.hbot.supervisor import Supervisor


async def handle_callback(method, params):
    return None


async def main():
    os.environ["AUTOPCR_HOSHINO_ENABLE_AUTOPCR"] = "false"
    supervisor = Supervisor(handle_callback)
    await supervisor.start()
    if not await supervisor.wait_ready(60):
        print("FAILED", flush=True)
        return 1
    print(supervisor._process.pid, flush=True)
    await asyncio.sleep(600)
    return 0


sys.exit(asyncio.get_event_loop().run_until_complete(main()))
"""


failures = []


def check(condition, description):
    if condition:
        print(f"  [通过] {description}")
    else:
        failures.append(description)
        print(f"  [失败] {description}")


def is_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def main():
    if not sys.platform.startswith("linux"):
        print("当前系统不提供父进程终止信号，跳过")
        return 0

    print("[1] 拉起宿主进程与 wrapper")
    workspace = tempfile.mkdtemp(prefix="orphan-host-")
    script = os.path.join(workspace, "host.py")
    with open(script, "w", encoding="utf-8") as fp:
        fp.write(HOST_SOURCE)

    environment = dict(os.environ)
    environment["AUTOPCR_HOSHINO_TEST_SYSPATH"] = os.path.dirname(PROJECT_ROOT)
    helper = subprocess.Popen(
        [sys.executable, script],
        stdout=subprocess.PIPE,
        cwd=workspace,
        env=environment,
    )
    line = helper.stdout.readline().decode().strip()
    check(line.isdigit(), f"宿主进程报告了 wrapper 进程号：{line}")
    if not line.isdigit():
        helper.kill()
        return 1

    wrapper_pid = int(line)
    check(is_alive(wrapper_pid), "wrapper 正在运行")

    print("\n[2] 强制终止宿主进程")
    helper.send_signal(signal.SIGKILL)
    helper.wait(timeout=10)
    check(True, "宿主进程已被强制终止，未执行任何清理逻辑")

    print("\n[3] wrapper 是否随之退出")
    deadline = time.time() + 20
    while is_alive(wrapper_pid) and time.time() < deadline:
        time.sleep(0.2)
    alive = is_alive(wrapper_pid)
    check(not alive, "wrapper 已退出，未成为孤儿进程")
    if alive:
        os.kill(wrapper_pid, signal.SIGKILL)

    print("\n" + "=" * 56)
    if failures:
        print(f"失败 {len(failures)} 项：")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("全部检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
