"""autopcr 接入实测。

在装有宿主框架依赖的解释器（Python 3.8）中运行，拉起启用了 autopcr 的 wrapper 子进程，
验证：

* autopcr 能在 wrapper 进程中被导入并完成网页端启动。
* 实际监听端口能上报回兼容层。
* 网页端能够响应请求，且能经由转发端点访问。

需要通过 ``AUTOPCR_HOSHINO_AUTOPCR_ROOT`` 指定 autopcr 源码位置。
母数据下载在后台进行，本测试不等待其完成。
"""
import asyncio
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from autopcr_hoshino.hbot.callbacks import CallbackHandler  # noqa: E402
from autopcr_hoshino.hbot.proxy import WebProxy  # noqa: E402
from autopcr_hoshino.hbot.supervisor import Supervisor  # noqa: E402

DEFAULT_AUTOPCR_ROOT = "/workspaces/go-autopcr/ref/autopcr_latest"

failures = []


def check(condition, description):
    if condition:
        print(f"  [通过] {description}")
    else:
        failures.append(description)
        print(f"  [失败] {description}")


class FakeService:
    """提供群成员名单，供号码校验使用。"""

    def __init__(self, groups):
        self._groups = groups
        self.bot = self

    async def get_enable_groups(self):
        return {gid: ["self"] for gid in self._groups}

    async def get_group_member_list(self, group_id, self_id=None):
        return [{"user_id": qq} for qq in self._groups.get(group_id, [])]


async def check_register_guard(port, groups):
    """注册接口应拒绝不在群内的号码。"""
    import aiohttp

    base = f"http://127.0.0.1:{port}/daily"
    timeout = aiohttp.ClientTimeout(total=15)
    headers = {"App-Version": "1.7"}
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.post(
            base + "/api/register", json={"qq": "99999999", "password": "x" * 8}
        ) as response:
            body = await response.text()
            check(
                response.status == 400 and "无效的QQ" in body,
                f"群外号码被拒绝：{response.status} {body[:30]}",
            )

        # 群内号码应通过校验，进入 autopcr 自身的注册流程。
        insider = str(next(iter(groups.values()))[0])
        async with session.post(
            base + "/api/register", json={"qq": insider, "password": "x" * 8}
        ) as response:
            body = await response.text()
            check(
                "无效的QQ" not in body,
                f"群内号码通过校验：{response.status} {body[:40]}",
            )


async def check_web(port):
    """检验网页端接口可用。

    前端静态资源由 autopcr 的 ``_download_web.py`` 单独下载，可能并未就绪，
    因此这里只请求接口，不请求页面。
    """
    import aiohttp

    base = f"http://127.0.0.1:{port}/daily"
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # 未登录访问受保护接口应被拒绝，据此确认应用逻辑而非静态文件在响应。
        async with session.get(base + "/api/account", allow_redirects=False) as response:
            check(
                response.status in (302, 401, 403),
                f"未登录访问受保护接口得到 {response.status}",
            )

        # autopcr 会校验前端版本，未带版本头的请求会被拒绝，
        # 这同样证明应用逻辑在响应而非静态文件在响应。
        async with session.post(
            base + "/api/login/qq", json={"qq": "", "password": ""}
        ) as response:
            body = await response.text()
            check(response.status == 400, f"登录接口拒绝了不合法的请求，状态码 {response.status}")
            check(bool(body.strip()), f"返回可读的提示：{body[:40]}")


async def check_through_proxy(supervisor):
    """经由兼容层的转发端点访问网页端。"""
    import aiohttp
    from hypercorn.asyncio import serve
    from hypercorn.config import Config
    from quart import Quart

    proxy = WebProxy(lambda: supervisor.web_port)
    app = Quart(__name__)
    app.register_blueprint(proxy.blueprint())

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    proxy_port = sock.getsockname()[1]
    sock.listen(128)
    sock.setblocking(False)

    config = Config()
    config.bind = [f"fd://{sock.fileno()}"]
    config.accesslog = None
    shutdown = asyncio.Event()
    task = asyncio.ensure_future(serve(app, config, shutdown_trigger=shutdown.wait))
    await asyncio.sleep(1.0)

    try:
        async with aiohttp.ClientSession() as session:
            url = f"http://127.0.0.1:{proxy_port}/daily/api/account"
            async with session.get(url, allow_redirects=False) as response:
                check(
                    response.status in (302, 401, 403),
                    f"经转发端点访问网页端接口得到 {response.status}",
                )
    finally:
        await proxy.close()
        shutdown.set()
        try:
            await asyncio.wait_for(task, 5)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            task.cancel()


async def main():
    autopcr_root = os.getenv("AUTOPCR_HOSHINO_AUTOPCR_ROOT", DEFAULT_AUTOPCR_ROOT)
    if not os.path.isdir(os.path.join(autopcr_root, "autopcr")):
        print(f"未找到 autopcr 源码：{autopcr_root}")
        return 1
    os.environ["AUTOPCR_HOSHINO_AUTOPCR_ROOT"] = autopcr_root
    os.environ["AUTOPCR_HOSHINO_ENABLE_AUTOPCR"] = "true"

    print("[1] 拉起启用 autopcr 的 wrapper")
    print(f"  autopcr 源码 {autopcr_root}")
    # 使用产品代码中的回调处理器，端口上报走真实路径。
    # 该路径只需要监督器本身，无需宿主框架的服务与会话表。
    state = {}
    groups = {20001: ["10001", "10002"]}
    supervisor = Supervisor(
        CallbackHandler(FakeService(groups), None, lambda: state.get("supervisor"))
    )
    state["supervisor"] = supervisor
    await supervisor.start()
    check(await supervisor.wait_ready(120), "wrapper 完成连接与认证")

    print("\n[2] 网页端启动与端口上报")
    deadline = asyncio.get_event_loop().time() + 180
    while supervisor.web_port is None and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.5)
    check(supervisor.web_port is not None, f"网页端端口已上报：{supervisor.web_port}")
    if supervisor.web_port is None:
        await supervisor.stop()
        return 1

    try:
        print("\n[3] 网页端直接访问")
        await check_web(supervisor.web_port)

        print("\n[4] 经转发端点访问")
        await check_through_proxy(supervisor)

        print("\n[5] 注册接口的号码校验")
        await check_register_guard(supervisor.web_port, groups)
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
