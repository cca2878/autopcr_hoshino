"""命令清单。

兼容层据此向宿主框架注册消息触发器，wrapper 据此把事件分发到对应实现。
两侧读取同一份定义，避免命令增删时两边不同步。

宿主框架的前缀触发器按最长前缀匹配，因此 :data:`PREFIX_COMMANDS` 中的
``COMMAND_PREFIX`` 是兜底项：所有未被更长前缀命中的消息都由它接收，
再由 wrapper 按工具名前缀匹配分发。
"""

#: 全部命令共用的前导字符。
COMMAND_PREFIX = "#"

#: 全字匹配触发的命令。消息需与之完全相同才触发。
FULLMATCH_COMMANDS = (
    "帮助自动清日常",
    COMMAND_PREFIX + "帮助",
    COMMAND_PREFIX + "清日常所有",
    COMMAND_PREFIX + "查禁用",
    COMMAND_PREFIX + "查群禁用",
    COMMAND_PREFIX + "查内鬼",
    COMMAND_PREFIX + "清内鬼",
    COMMAND_PREFIX + "运行状态",
    COMMAND_PREFIX + "配置日常",
    COMMAND_PREFIX + "卡池",
)

#: 前缀匹配触发的命令，其后可跟参数。
PREFIX_COMMANDS = (
    COMMAND_PREFIX + "清日常",
    COMMAND_PREFIX + "日常报告",
    COMMAND_PREFIX + "日常记录",
    COMMAND_PREFIX + "定时日志",
    COMMAND_PREFIX + "定时状态",
    COMMAND_PREFIX + "定时统计",
    COMMAND_PREFIX + "识图",
    COMMAND_PREFIX,
)


#: 指令说明。兼容层用它填充服务的帮助信息，wrapper 用它渲染帮助图片。
SV_HELP = """
- {p}配置日常 一切的开始
- {p}清日常 [昵称] 无昵称则默认账号
- {p}清日常所有 清该qq号下所有号的日常
指令格式： 命令 昵称 参数，下述省略昵称，<>表示必填，[]表示可选，|表示分割
- {p}日常记录 查看清日常状态
- {p}日常报告 [0|1|2|3] 最近四次清日常报告
- {p}定时日志 查看定时运行状态
- {p}查角色 [昵称] 查看角色练度
- {p}查缺角色 查看缺少的限定常驻角色
- {p}查ex装备 [会战] 查看ex装备库存
- {p}查探险编队 根据记忆碎片角色编队战力相当的队伍
- {p}查兑换角色碎片 [开换] 查询兑换特别角色的记忆碎片策略
- {p}查心碎 查询缺口心碎
- {p}查纯净碎片 查询缺口纯净碎片，国服六星+日服二专需求
- {p}查记忆碎片 [可刷取|大师币] 查询缺口记忆碎片，可按地图可刷取或大师币商店过滤
- {p}查装备 [<rank>] [fav] 查询缺口装备，rank为数字，只查询>=rank的角色缺口装备，fav表示只查询favorite的角色
- {p}查深域 查询深域通关情况
- {p}查公会深域 查询公会深域通关情况
- {p}黎明界开局 <美食殿堂|破晓之星|咲恋救济院|王宫骑士团|拉比林斯> 可以只打部分字
- {p}刷图推荐 [<rank>] [fav] 查询缺口装备的刷图推荐，格式同上
- {p}公会支援 查询公会支援角色配置
- {p}卡池 查看当前卡池
- {p}编队 1 1 春妈 蝶妈 狗妈 水妈 礼妈 便捷设置编队
- {p}一键编队 1 1 [拉满] 队名1 星级角色1 星级角色2 ... 星级角色5 队名2 星级角色1 星级角色2 设置多队编队，一行一个队伍
- {p}半月刊 查看半月刊
- {p}识图 [图片] 识别图片中的角色，返回一键编队文本
- {p}免费十连 <卡池id> 卡池id来自【{p}卡池】
- {p}来发十连 <卡池id> [抽到出] [单抽券|单抽] [编号小优先] [开抽] 赛博抽卡，谨慎使用。卡池id来自【{p}卡池】，[抽到出]表示抽到出货或达天井，默认十连，[单抽券]表示仅用厕纸，[单抽]表示宝石单抽，[标号小优先]指智能pickup时优先选择编号小的角色，[开抽]表示确认抽卡。已有up也可再次触发。
""".strip().format(
    p=COMMAND_PREFIX
)


#: wrapper 可以向兼容层发起的调用。兼容层只接受此表内的方法名。
#: 前五项针对某次具体事件，需携带 ``session_id``；``report_web_port`` 与事件无关。
CALLBACK_METHODS = (
    "send",
    "finish",
    "get_group_member_list",
    "call_action",
    "upload_file",
    "filter_invalid_qq",
    "report_web_port",
)

#: 兼容层可以向 wrapper 发起的调用。``echo`` 仅用于排障。
COMMAND_METHODS = (
    "dispatch",
    "ping",
    "echo",
)
