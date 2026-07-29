"""autopcr 运行时的启动编排。

三条任务并列运行，互不接管对方的事件循环：

* 网页端服务，由 hypercorn 直接驱动 autopcr 的 Quart 应用。
* 母数据初始化。
* 定时任务调度。

不使用 autopcr 自带的 ``HttpServer.run_forever``。该方法调用 ``Quart.run``，
后者在返回前会取消循环上的全部任务并关闭事件循环，无法与其他长期任务共存；
且其 ``use_reloader`` 参数默认为真，触发时会以 ``os.execv`` 替换整个进程，
连同与兼容层的连接一并失效。hypercorn 的配置项默认不启用重载器。

网页端监听端口默认由系统分配：先创建套接字并绑定，再以 ``fd://`` 形式交给 hypercorn，
由此在服务启动前即可得知实际端口并上报给兼容层。
"""
import asyncio
import logging
import socket
from typing import Callable, Optional, Tuple

from . import config

logger = logging.getLogger("autopcr_hoshino.wrapper.runtime")


def _bind_web_socket() -> Tuple[socket.socket, int]:
    """创建并启用监听套接字，返回它与实际端口。

    套接字以 ``fd://`` 形式交给 hypercorn，该形式要求传入的套接字已处于监听状态：
    hypercorn 只会包装文件描述符，不会代为 ``listen``。
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((config.WEB_HOST, config.WEB_PORT))
    sock.listen(config.WEB_BACKLOG)
    sock.setblocking(False)
    return sock, sock.getsockname()[1]


async def run(on_web_port: Optional[Callable[[int], None]] = None) -> None:
    """启动 autopcr 并持续运行。"""
    from autopcr.db.dbstart import db_start
    from autopcr.http_server.httpserver import HttpServer
    from autopcr.module.crons import queue_crons
    from hypercorn.asyncio import serve
    from hypercorn.config import Config

    sock, port = _bind_web_socket()

    # qq_mod 会让注册接口反向导入宿主插件包中的号码校验函数，该导入路径在独立进程中不存在。
    server = HttpServer(host=config.WEB_HOST, port=port, qq_mod=False)
    server.quart.register_blueprint(server.app)

    hypercorn_config = Config()
    hypercorn_config.bind = [f"fd://{sock.fileno()}"]
    hypercorn_config.accesslog = None
    hypercorn_config.errorlog = logger

    if on_web_port is not None:
        on_web_port(port)

    queue_crons()
    logger.info("autopcr 网页端启动于 %s:%s", config.WEB_HOST, port)
    await asyncio.gather(
        serve(server.quart, hypercorn_config),
        db_start(),
    )
