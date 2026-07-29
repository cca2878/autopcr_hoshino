"""孤儿进程实测所用的辅助进程。

拉起 wrapper，把其进程号写入标准输出后保持运行，等待被强制终止。
文件名以下划线开头，宿主框架的模块加载流程会跳过它。
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from autopcr_hoshino.hbot.supervisor import Supervisor  # noqa: E402


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


if __name__ == "__main__":
    sys.exit(asyncio.get_event_loop().run_until_complete(main()))
