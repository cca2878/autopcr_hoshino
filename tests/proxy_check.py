"""反向代理测试。

在装有宿主框架依赖的解释器（Python 3.8 / Quart 0.14）中运行，验证转发端点
能够在该版本的框架上正常工作，重点在于事件流是否**边收边发**——
若被整体缓冲，网页端的验证码推送将完全失效。
"""
import asyncio
import os
import socket
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPSTREAM_PYTHON = os.path.join(PROJECT_ROOT, ".venv-autopcr", "bin", "python")

#: 上游服务的源码。它模拟 autopcr 网页端提供的几类响应：服务端推送的事件流、
#: 普通 JSON、大体积响应与请求回显。运行时写入临时目录，作为子进程启动，
#: 因此不作为独立文件进入版本控制。
UPSTREAM_SOURCE = """
import asyncio
import socket
import sys

from quart import Quart, Response, request

app = Quart(__name__)


@app.route("/daily/api/sse")
async def sse():
    async def generate():
        for index in range(5):
            yield f"id: {index}\\ndata: message-{index}\\n\\n".encode()
            await asyncio.sleep(0.2)

    return Response(
        generate(),
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "X-Upstream-Marker": "sse",
        },
    )


@app.route("/daily/api/json")
async def json_endpoint():
    return {"ok": True, "text": "日常清理完毕"}, 200


@app.route("/daily/api/big")
async def big():
    return Response(
        b"X" * (5 * 1024 * 1024), headers={"Content-Type": "application/octet-stream"}
    )


@app.route("/daily/api/echo", methods=["POST"])
async def echo():
    body = await request.get_data()
    return Response(
        body,
        status=201,
        headers={
            "Content-Type": request.headers.get("Content-Type", ""),
            "X-Echo-Length": str(len(body)),
        },
    )


@app.route("/daily/")
@app.route("/daily/<path:path>")
async def index(path=""):
    return Response(f"index:{path}", headers={"Content-Type": "text/plain"})


async def main(port_file):
    from hypercorn.asyncio import serve
    from hypercorn.config import Config

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    with open(port_file, "w") as fp:
        fp.write(str(sock.getsockname()[1]))

    config = Config()
    config.bind = [f"fd://{sock.fileno()}"]
    config.accesslog = None
    await serve(app, config)


asyncio.run(main(sys.argv[1]))
"""


failures = []


def check(condition, description):
    if condition:
        print(f"  [通过] {description}")
    else:
        failures.append(description)
        print(f"  [失败] {description}")


def start_upstream():
    """把上游服务写入临时目录并启动，返回其进程与端口。"""
    workspace = tempfile.mkdtemp(prefix="proxy-upstream-")
    script = os.path.join(workspace, "upstream.py")
    with open(script, "w", encoding="utf-8") as fp:
        fp.write(UPSTREAM_SOURCE)
    port_file = os.path.join(workspace, "port")

    process = subprocess.Popen([UPSTREAM_PYTHON, script, port_file], cwd=workspace)
    deadline = time.time() + 60
    while time.time() < deadline:
        if os.path.exists(port_file):
            with open(port_file) as fp:
                content = fp.read().strip()
            if content:
                return process, int(content)
        if process.poll() is not None:
            raise RuntimeError("上游服务启动失败")
        time.sleep(0.2)
    raise RuntimeError("等待上游服务超时")


async def run_checks(proxy_port):
    import aiohttp

    base = f"http://127.0.0.1:{proxy_port}/daily"
    async with aiohttp.ClientSession() as session:
        print("\n[2] 普通响应")
        async with session.get(base + "/api/json") as response:
            data = await response.json()
            check(response.status == 200, "状态码为 200")
            check(data.get("text") == "日常清理完毕", "响应体内容正确")

        print("\n[3] 事件流是否边收边发")
        arrivals = []
        start = time.monotonic()
        async with session.get(
            base + "/api/sse", headers={"Accept": "text/event-stream"}
        ) as response:
            check(
                response.headers.get("Content-Type") == "text/event-stream",
                "内容类型原样透传",
            )
            check(
                response.headers.get("X-Upstream-Marker") == "sse",
                "自定义首部原样透传",
            )
            async for chunk in response.content.iter_any():
                if chunk.strip():
                    arrivals.append((time.monotonic() - start, chunk))
        check(len(arrivals) >= 5, f"五条事件全部到达，实收 {len(arrivals)} 段")
        if len(arrivals) >= 2:
            spread = arrivals[-1][0] - arrivals[0][0]
            check(
                spread > 0.5,
                f"各段到达时间跨度 {spread:.2f}s，确为流式而非整体缓冲",
            )
        body = b"".join(chunk for _, chunk in arrivals)
        check(b"message-4" in body, "事件内容完整")

        print("\n[4] 大体积响应")
        async with session.get(base + "/api/big") as response:
            payload = await response.read()
            check(len(payload) == 5 * 1024 * 1024, f"5 MB 响应完整，实收 {len(payload)} 字节")

        print("\n[5] 请求体与状态码转发")
        async with session.post(
            base + "/api/echo",
            data=b"a" * 100000,
            headers={"Content-Type": "application/octet-stream"},
        ) as response:
            payload = await response.read()
            check(response.status == 201, "上游状态码原样返回")
            check(len(payload) == 100000, "请求体完整送达并回显")
            check(response.headers.get("X-Echo-Length") == "100000", "上游首部原样返回")

        print("\n[6] 路径与查询串")
        async with session.get(base + "/some/nested/path?a=1&b=2") as response:
            text = await response.text()
            check(text == "index:some/nested/path", "多级路径正确转发")


async def check_not_ready(proxy_port):
    """wrapper 未就绪时应给出明确提示而非连接错误。"""
    import aiohttp

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"http://127.0.0.1:{proxy_port}/daily/api/json"
        ) as response:
            check(response.status == 503, "服务未就绪时返回 503")
            check("尚未就绪" in await response.text(), "未就绪提示可读")


async def main():
    import importlib.metadata as metadata

    from autopcr_hoshino.hbot.proxy import WebProxy
    from quart import Quart

    print("[1] 启动上游服务与转发端点")
    print(f"  兼容层解释器 {sys.version.split()[0]}")
    print("  兼容层 Quart {}".format(metadata.version("Quart")))

    upstream, upstream_port = start_upstream()
    print(f"  上游监听于 127.0.0.1:{upstream_port}")

    # 端口按请求读取，据此可以在运行中模拟 wrapper 尚未就绪的状态。
    port_holder = {"port": upstream_port}
    proxy = WebProxy(lambda: port_holder["port"])
    app = Quart(__name__)
    app.register_blueprint(proxy.blueprint())

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    proxy_port = sock.getsockname()[1]
    sock.listen(128)
    sock.setblocking(False)

    from hypercorn.asyncio import serve
    from hypercorn.config import Config

    config = Config()
    config.bind = [f"fd://{sock.fileno()}"]
    config.accesslog = None

    shutdown = asyncio.Event()
    server_task = asyncio.ensure_future(
        serve(app, config, shutdown_trigger=shutdown.wait)
    )
    await asyncio.sleep(1.0)
    print(f"  转发端点监听于 127.0.0.1:{proxy_port}")

    try:
        await run_checks(proxy_port)
        print("\n[7] wrapper 未就绪时的处理")
        port_holder["port"] = None
        await check_not_ready(proxy_port)
    finally:
        await proxy.close()
        shutdown.set()
        try:
            await asyncio.wait_for(server_task, 5)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            server_task.cancel()
        upstream.terminate()
        upstream.wait(timeout=10)

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
