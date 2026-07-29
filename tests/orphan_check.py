"""孤儿进程实测。

宿主进程被强制终止时不会执行任何清理逻辑，wrapper 若继续运行便会占住端口
并持续访问游戏接口。本测试验证内核层面的兜底机制生效：

* 强制终止宿主进程后，wrapper 随之退出。

该机制依赖 Linux 的父进程终止信号，在其他系统上本测试跳过。
"""
import os
import signal
import subprocess
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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
    helper = subprocess.Popen(
        [sys.executable, os.path.join(PROJECT_ROOT, "tests", "_orphan_helper.py")],
        stdout=subprocess.PIPE,
        cwd=PROJECT_ROOT,
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
