"""消息文本处理。

autopcr 的绘图工具直接产出 CQ 码形式的图片消息，因此 wrapper 需要按同一套规则
转义拼接进消息的用户输入，避免昵称中的方括号等字符破坏消息结构。
"""


def escape(text: str, escape_comma: bool = True) -> str:
    """对字符串进行 CQ 码转义。"""
    text = text.replace("&", "&amp;").replace("[", "&#91;").replace("]", "&#93;")
    if escape_comma:
        text = text.replace(",", "&#44;")
    return text
