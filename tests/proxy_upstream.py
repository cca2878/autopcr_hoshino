"""反向代理测试所用的上游服务。

在装有 autopcr 依赖的解释器（Python 3.10 / Quart 0.19）中运行，
模拟 autopcr 网页端提供的几类响应：服务端推送的事件流、普通 JSON、
大体积响应与请求回显。

实际监听端口写入由命令行给出的文件，供测试进程读取。
"""
import asyncio
import socket
import sys

from quart import Quart, Response, request

app = Quart(__name__)


@app.route("/daily/api/sse")
async def sse():
    """每隔一段时间推送一条事件，用于检验转发是否为流式。"""

    async def generate():
        for index in range(5):
            yield f"id: {index}\ndata: message-{index}\n\n".encode()
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
    return Response(b"X" * (5 * 1024 * 1024), headers={"Content-Type": "application/octet-stream"})


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


async def main(port_file: str):
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


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
