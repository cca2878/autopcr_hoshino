"""处理 wrapper 发来的调用。

wrapper 无法直接操作宿主框架，凡是需要当场发消息、查询群信息或上传文件的动作
都由本模块代为执行。
"""
import base64
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger("autopcr_hoshino.callbacks")


class CallbackHandler:
    """把 wrapper 的调用转换为对宿主框架的操作。"""

    def __init__(self, service, sessions, supervisor_ref):
        self._service = service
        self._sessions = sessions
        self._supervisor_ref = supervisor_ref

    async def __call__(self, method: str, params: Dict[str, Any]) -> Any:
        handler = getattr(self, "_on_" + method, None)
        if handler is None:
            raise ValueError(f"未知的回调：{method}")
        return await handler(params)

    def _session(self, params):
        session = self._sessions.get(params.get("session_id"))
        if session is None:
            raise ValueError("会话已结束：{}".format(params.get("session_id")))
        return session

    # ---------------------------------------------------------------- 消息发送

    async def _on_send(self, params):
        session = self._session(params)
        message = "[CQ:reply,id={}]{}".format(
            session.event.message_id, params.get("msg", "")
        )
        await session.bot.send(session.event, message)

    async def _on_finish(self, params):
        # 终止处理链的动作由 wrapper 侧在发出本调用后自行完成，
        # 此处只负责把最终答复发出去。
        session = self._session(params)
        await session.bot.send(session.event, params.get("msg", ""))

    # ---------------------------------------------------------------- 群信息查询

    async def _on_get_group_member_list(self, params):
        session = self._session(params)
        members = await session.bot.get_group_member_list(
            group_id=session.event.group_id
        )
        result = [
            (str(m["user_id"]), m["card"] if m.get("card") else m["nickname"])
            for m in members
        ]
        return sorted(result, key=lambda item: item[1])

    async def _on_call_action(self, params):
        session = self._session(params)
        return await session.bot.call_action(
            params["action"], **(params.get("params") or {})
        )

    async def _on_filter_invalid_qq(self, params) -> List[str]:
        """挑出已不在任何启用群内的号码。

        成员名单按群拉取一次即可覆盖全部待判定号码，
        因此这里一次性完成判定，而不是逐个号码重复拉取。
        """
        bot = self._service.bot
        enable_groups = await self._service.get_enable_groups()

        known_members = set()
        for group_id, self_ids in enable_groups.items():
            for self_id in self_ids:
                try:
                    members = await bot.get_group_member_list(
                        group_id=group_id, self_id=self_id
                    )
                except Exception:
                    continue
                known_members.update(str(m["user_id"]) for m in members)
                break

        invalid = []
        for qq in params.get("qqs", []):
            qq = str(qq)
            if qq.startswith("g"):
                group_id = qq[1:]
                if not (group_id.isdigit() and int(group_id) in enable_groups):
                    invalid.append(qq)
            elif qq not in known_members:
                invalid.append(qq)
        return invalid

    # ---------------------------------------------------------------- 文件上传

    async def _on_upload_file(self, params):
        """把文件写入宿主框架的资源目录后上传到群。

        资源目录及其对外地址属于宿主框架的配置，因此落盘与上传都在本端完成。
        """
        from hoshino import R

        session = self._session(params)
        filename = params["filename"]
        folder_name = params.get("folder_name")
        content = base64.b64decode(params["content"])

        resource = R.get("autopcr", "excel", filename)
        path = Path(resource.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

        try:
            group_id = session.event.group_id
            upload_params = {
                "group_id": group_id,
                "file": resource.url,
                "name": filename,
            }
            if folder_name:
                folder_id = await self._resolve_folder(session, folder_name)
                if folder_id:
                    upload_params["folder"] = folder_id
                else:
                    await session.bot.send(
                        session.event, "未能获取文件夹ID，上传到根目录"
                    )
            await session.bot.call_action("upload_group_file", **upload_params)
        finally:
            try:
                path.unlink()
            except OSError as exc:
                logger.warning("删除临时文件失败：%s", exc)

    async def _resolve_folder(self, session, folder_name):
        """查找群文件夹，不存在时尝试创建。"""
        try:
            group_id = session.event.group_id
            response = await session.bot.call_action(
                "get_group_root_files", group_id=group_id
            )
            for folder in response.get("folders", []):
                if folder.get("folder_name") == folder_name:
                    return folder.get("folder_id")

            await session.bot.send(
                session.event,
                f"本群 {group_id} 未找到「{folder_name}」，尝试创建...",
            )
            # 不同的机器人实现使用不同的参数名，两个都传以兼容。
            created = await session.bot.call_action(
                "create_group_file_folder",
                group_id=group_id,
                folder_name=folder_name,
                name=folder_name,
            )
            folder_id = created.get("folder_id")
            if not folder_id:
                raise RuntimeError("非管理员无法创建文件夹")
            return folder_id
        except Exception as exc:
            await session.bot.send(
                session.event, f"获取或创建「{folder_name}」文件夹失败: {exc}"
            )
            return None

    # ---------------------------------------------------------------- 状态上报

    async def _on_report_web_port(self, params):
        supervisor = self._supervisor_ref()
        if supervisor is not None:
            supervisor.set_web_port(int(params["port"]))
