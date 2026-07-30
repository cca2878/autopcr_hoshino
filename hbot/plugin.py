"""在宿主框架中注册服务、命令与网页端入口。

命令处理函数只做三件事：拆解消息、把事件交给 wrapper、在处理结束后清理会话。
全部业务逻辑都在 wrapper 中执行。
"""
import asyncio
import logging
import socket

from ..catalog import COMMAND_PREFIX, FULLMATCH_COMMANDS, PREFIX_COMMANDS, SV_HELP
from . import config, provision, settings
from .callbacks import CallbackHandler
from .event import SessionRegistry, build_payload
from .proxy import WebProxy
from .supervisor import Supervisor, WrapperUnavailable

logger = logging.getLogger("autopcr_hoshino")

_state = {}


def resolve_web_address() -> str:
    """确定网页端对外地址。

    依次尝试环境变量、宿主框架配置与本机地址解析，均不可得时退回回环地址。
    """
    address = settings.get("autopcr_public_address")

    if not address:
        try:
            from hoshino.config import PUBLIC_ADDRESS

            address = PUBLIC_ADDRESS
        except Exception:
            pass

    if not address:
        try:
            address = socket.gethostbyname(socket.gethostname())
        except Exception:
            pass

    if not address:
        address = "127.0.0.1"

    scheme = "https://" if settings.get_bool("autopcr_use_https", False) else "http://"
    return scheme + address + config.web_path_prefix() + "/"


def setup():
    """创建服务并完成全部注册。返回创建的服务对象。"""
    import nonebot
    from hoshino import Service, priv
    from nonebot import on_startup

    service = Service(
        name="自动清日常",
        use_priv=priv.NORMAL,
        manage_priv=priv.ADMIN,
        visible=False,
        enable_on_default=False,
        bundle="pcr工具",
        help_=SV_HELP,
    )

    sessions = SessionRegistry()
    provisioner = None
    if provision.is_managed():
        provisioner = provision.provision
        logger.info(
            "未指定 autopcr 位置，将自动准备（%s）", provision.describe_requirements()
        )
    logger.info("配置来源：%s", settings.describe_source())
    supervisor = Supervisor(
        CallbackHandler(service, sessions, lambda: _state.get("supervisor")),
        provisioner=provisioner,
    )
    _state["supervisor"] = supervisor
    _state["service"] = service
    _state["web_address"] = resolve_web_address()

    def make_handler(command: str):
        async def handler(bot, event):
            session = sessions.open(bot, event)
            try:
                payload = build_payload(session, command, _state["web_address"])
                await supervisor.call("dispatch", command=command, event=payload)
            except WrapperUnavailable as exc:
                await bot.send(event, str(exc))
            except asyncio.TimeoutError:
                await bot.send(event, "autopcr 服务响应超时")
            except Exception:
                # 命令自身的错误已由 wrapper 处理并回报，能到达此处的是链路层面的故障。
                logger.exception("处理命令 %s 失败", command)
                await bot.send(event, "autopcr 服务异常，请查看日志")
            finally:
                sessions.close(session)

        # 宿主框架用函数名标识处理器，兜底前缀去掉前导字符后为空，另行命名。
        handler.__name__ = "autopcr_" + (command.lstrip(COMMAND_PREFIX) or "tool")
        return handler

    for command in FULLMATCH_COMMANDS:
        service.on_fullmatch(command)(make_handler(command))
    for command in PREFIX_COMMANDS:
        service.on_prefix(command)(make_handler(command))

    app = nonebot.get_bot().server_app

    if config.web_proxy_enabled():
        proxy = WebProxy(lambda: supervisor.web_port, config.web_path_prefix())
        _state["proxy"] = proxy
        app.register_blueprint(proxy.blueprint())
        logger.info("autopcr 网页端将由 %s 转发", config.web_path_prefix())

    @on_startup
    async def start_wrapper():
        await supervisor.start()

    @app.after_serving
    async def stop_wrapper():
        """宿主框架退出时终止 wrapper 并释放转发所用的连接池。"""
        await supervisor.stop()
        if _state.get("proxy") is not None:
            await _state["proxy"].close()

    return service
