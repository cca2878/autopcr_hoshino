"""autopcr_hoshino 配置模板。

把本文件复制到宿主框架的配置目录并按插件名命名，即 ``hoshino/config/autopcr_hoshino.py``，
然后按需修改。全部配置项均可省略，省略时使用注释中标明的默认值。

同名环境变量（配置项名加 ``AUTOPCR_HOSHINO_`` 前缀）优先于本文件。

文件名以下划线开头，宿主框架的模块扫描会跳过它。
"""

# ---------------------------------------------------------------- 自动准备
#
# 未设置 AUTOPCR_ROOT 时，首次启动会自动取得 autopcr 源码、创建运行环境并安装依赖。
# 该过程需要 git，以及 uv 或一个 Python 3.10 解释器之一。

# 是否启用自动准备。关闭后需自行准备环境并设置 AUTOPCR_ROOT。
# AUTO_PROVISION = True

# 自动准备时使用的仓库。
# AUTOPCR_REPO = "https://github.com/cc004/autopcr"

# 检出的分支或标签，留空则使用远端默认分支。
# AUTOPCR_REF = ""

# 每次启动是否尝试更新源码。默认关闭：上游改动在无人值守时生效的风险高于收益。
# 更新只做快进式合并，检测到本地改动时跳过，不会触碰账号数据。
# AUTO_UPDATE = False

# 源码与数据的存放位置。账号配置与母数据位于其下的 cache 目录，备份时取该目录。
# 若置于插件目录内，名称必须以点或下划线开头，否则会被宿主框架误当作插件加载。
# MANAGED_ROOT = ".autopcr"

# 运行环境的存放位置。
# MANAGED_VENV = ".venv-autopcr"

# 自动准备运行环境时使用的 Python 版本。
# AUTOPCR_PYTHON_VERSION = "3.10"

# ---------------------------------------------------------------- 自行管理
#
# 设置 AUTOPCR_ROOT 即视为自行管理，自动准备不进行。

# autopcr 源码根目录，即包含 autopcr 包的那一层。
# AUTOPCR_ROOT = "/path/to/autopcr"

# 运行 wrapper 的解释器，其所在环境需安装 autopcr 的依赖。
# PYTHON = ".venv-autopcr/bin/python"

# ---------------------------------------------------------------- 网页端

# 是否在宿主框架上转发 autopcr 网页端。关闭后需直接访问 wrapper 监听的端口。
# WEB_PROXY = True

# 转发时使用的路径前缀，需与 autopcr 自身的前缀一致。
# WEB_PREFIX = "/daily"

# wrapper 网页端监听的地址与端口。端口取 0 时由系统分配。
# WEB_HOST = "127.0.0.1"
# WEB_PORT = 0

# 监听队列长度，一般无需调整。
# WEB_BACKLOG = 128

# 是否启动 autopcr。关闭后 wrapper 仅保留通信能力，用于排障。
# ENABLE_AUTOPCR = True

# 网页端注册是否要求号码在机器人所在的群内。
# VERIFY_REGISTER = True

# 网页端对外地址，用于生成配置页与验证码链接。
# 留空则依次尝试宿主框架的 PUBLIC_ADDRESS 与本机地址解析。
# AUTOPCR_PUBLIC_ADDRESS = ""

# 对外地址是否使用 HTTPS。
# AUTOPCR_USE_HTTPS = False

# ---------------------------------------------------------------- 进程管理

# wrapper 意外退出后的重启间隔秒数，连续失败时逐次加倍。
# RESTART_DELAY = 5

# 重启间隔的上限秒数。
# MAX_RESTART_DELAY = 300

# 一次运行持续超过该秒数即视为正常，重启间隔随之重置。
# HEALTHY_UPTIME = 60

# 等待 wrapper 就绪的秒数。
# STARTUP_TIMEOUT = 180
