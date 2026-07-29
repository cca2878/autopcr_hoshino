"""autopcr 的 HoshinoBot 兼容层。

autopcr 与 HoshinoBot 对 Quart、Jinja2、MarkupSafe、Pillow 的版本要求互不相容，
无法安装在同一环境中。本项目把 autopcr 移入独立解释器运行的子进程，
在宿主框架一侧只保留消息收发与权限判定，两者通过回环地址上的通信链路协作。

本模块不含任何副作用。服务注册由 :mod:`autopcr_hoshino.entry` 在被宿主框架加载时完成。
"""
