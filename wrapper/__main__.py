"""wrapper 进程入口。

由兼容层以子进程方式启动，不支持单独运行：进程间通信所需的端口与密钥
由兼容层通过环境变量注入。

与兼容层的连接断开即退出，由兼容层负责重新拉起。
"""
import asyncio
import logging
import sys

from ..protocol import Peer, perform_handshake
from . import config, runtime
from .service import WrapperService

logger = logging.getLogger("autopcr_hoshino.wrapper")


def _configure_logging() -> None:
    """把日志输出到标准错误。

    进程间通信走独立的套接字，标准输出与标准错误不承载任何协议数据，
    因此 autopcr 及其依赖可以自由打印日志，无需为通信让路。
    """
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    )


async def main() -> int:
    _configure_logging()

    service = WrapperService()

    reader, writer = await asyncio.open_connection("127.0.0.1", config.rpc_port())
    await perform_handshake(reader, writer, config.rpc_key())
    peer = Peer(reader, writer, service.handle, name="兼容层")
    service.attach(peer)
    logger.info("已连接至兼容层")

    tasks = [asyncio.ensure_future(peer.run())]
    if config.AUTOPCR_ENABLED:
        tasks.append(asyncio.ensure_future(runtime.run(service.report_web_port)))
    else:
        logger.warning("autopcr 未启用，仅提供通信能力")

    # 任一任务结束即退出：连接断开后应由兼容层重新拉起，
    # 网页端异常终止时也不应留下一个只能收发消息的空壳进程。
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    for task in done:
        exc = task.exception()
        if exc is not None:
            logger.error("wrapper 因异常退出：%r", exc)
            return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.get_event_loop().run_until_complete(main()))
    except KeyboardInterrupt:
        sys.exit(0)
