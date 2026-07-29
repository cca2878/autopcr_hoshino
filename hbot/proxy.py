"""autopcr 网页端的反向代理。

autopcr 的网页端运行在 wrapper 进程中，监听独立端口。若让用户直接访问该端口，
既需要额外开放端口，也使访问地址与宿主框架不一致。因此在宿主框架的应用上注册
一个转发端点，把原有路径下的请求原样转交给 wrapper。

转发不解析业务语义，仅在网络层搬运字节。响应以流式转发，
使服务端推送的事件流能够即时到达浏览器，而不是等到连接结束才整体送出。
"""
import logging
from typing import Callable, Optional

logger = logging.getLogger("autopcr_hoshino.proxy")

#: 逐跳首部，只在单个连接上有意义，不得转发。
#: ``content-length`` 一并去除，因为响应以流式重新分块发出。
HOP_BY_HOP_HEADERS = frozenset(
    [
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "host",
        "content-length",
    ]
)

#: 允许转发的请求方法。
ALLOWED_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]


def _filter_headers(headers):
    return [(key, value) for key, value in headers if key.lower() not in HOP_BY_HOP_HEADERS]


class WebProxy:
    """把宿主框架收到的网页请求转交给 wrapper。

    ``get_web_port`` 返回 wrapper 网页端当前的端口，未就绪时返回 ``None``。
    端口在每次请求时读取，因此 wrapper 重启后换用新端口无需重新注册。
    """

    def __init__(self, get_web_port: Callable[[], Optional[int]], path_prefix: str = "/daily"):
        self._get_web_port = get_web_port
        self._path_prefix = path_prefix
        self._session = None

    def _client_session(self):
        import aiohttp

        if self._session is None or self._session.closed:
            # 不设总超时：事件流与清日常结果都可能长时间保持连接，
            # 只对建立连接的过程设限。
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=None, sock_connect=10),
                auto_decompress=False,
            )
        return self._session

    async def close(self) -> None:
        """释放转发所用的连接池。"""
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _forward(self, path: str):
        import aiohttp
        from quart import Response, request

        port = self._get_web_port()
        if port is None:
            return Response("autopcr 服务尚未就绪，请稍后再试", status=503)

        target = f"http://127.0.0.1:{port}{self._path_prefix}/{path}"
        if request.query_string:
            target += "?" + request.query_string.decode("ascii")

        body = await request.get_data()

        try:
            upstream = await self._client_session().request(
                request.method,
                target,
                headers=_filter_headers(request.headers.items()),
                data=body if body else None,
                allow_redirects=False,
            )
        except aiohttp.ClientError as exc:
            logger.warning("转发至 %s 失败：%s", target, exc)
            return Response(f"无法连接 autopcr 服务：{exc}", status=502)

        async def stream():
            try:
                async for chunk in upstream.content.iter_any():
                    yield chunk
            finally:
                upstream.release()

        return Response(
            stream(),
            status=upstream.status,
            headers=_filter_headers(upstream.headers.items()),
        )

    def blueprint(self):
        """构造可注册到宿主框架应用上的转发端点。"""
        from quart import Blueprint

        blueprint = Blueprint("autopcr_web", __name__)
        blueprint.add_url_rule(
            self._path_prefix,
            "forward_root",
            lambda: self._forward(""),
            methods=ALLOWED_METHODS,
        )
        blueprint.add_url_rule(
            self._path_prefix + "/<path:path>",
            "forward",
            self._forward,
            methods=ALLOWED_METHODS,
        )
        return blueprint
