<!-- 职责：记录 AstrBot 对第三方插件的硬性要求与可用接口，供本插件实现时对照；不写本插件自身的工具设计与取舍。 -->

# AstrBot 插件开发约束

资料采集自上游仓库 `E:\Code\Projects\Applications\AstrBot\upstream\AstrBot`（采集日期 2026-10-26）。文中行号对应该时点的上游代码，上游更新后可能漂移。

## 元数据与目录

`metadata.yaml`（或 `metadata.yml`）是插件被识别的唯一依据。

必填字段（`astrbot/core/star/updater.py:360` 的 `validate_plugin_metadata`）：

| 字段 | 要求 |
|---|---|
| `name` | 非空字符串，即插件目录名，必须与仓库名一致 |
| `author` | 非空字符串 |
| `desc` | 非空字符串（可写 `description`，会被归一化到 `desc`） |
| `version` | 非空字符串 |

可选字段：

| 字段 | 说明 |
|---|---|
| `display_name` | WebUI 与插件市场的展示名 |
| `short_desc` | 市场卡片短描述，缺省回退 `desc` |
| `repo` | 仓库地址 |
| `astrbot_version` | PEP 440 范围，**不带 `v` 前缀**，如 `>=4.16,<5`；不满足时阻止加载 |
| `support_platforms` | 声明支持的平台适配器 key 列表，仅用于展示 |

目录名解析见 `astrbot/core/star/star_manager.py:642` 的 `_get_plugin_dir_name_from_metadata`：没有 `metadata.yaml` 时无法确定目录名，插件不会被加载。

可选目录：

```
<plugin>/
  metadata.yaml
  main.py
  requirements.txt
  _conf_schema.json
  logo.png
  skills/            # 每个 Skill 一个子目录，内含 SKILL.md
```

## 生命周期与入口

```python
from astrbot.api import logger, star
from astrbot.api import AstrBotConfig


class Main(star.Star):
    def __init__(self, context: star.Context, config: AstrBotConfig) -> None:
        super().__init__(context)

    async def terminate(self) -> None:
        ...
```

- 只有两个生命周期点：`__init__` 与 `async terminate()`。
- 插件在运行时注入，调试需启动 AstrBot 本体；WebUI 插件页可热重载。
- `self.logger` 自动注入，等级可在 WebUI 单独设置；也可 `from astrbot.api import logger`，会按调用位置路由到当前插件 logger。
- 不要用标准库 `logging`。

## 工具注册

### 注册入口

```python
self.context.add_llm_tools(MyTool(), OtherTool())
```

见 `astrbot/core/star/context.py:738`。行为：

- 同名工具会被**替换**（先 `remove_func` 再 append），并打 warning。
- 自动写入 `handler_module_path`，用于把工具归属到插件。
- `context.register_llm_tool()` 已废弃，不要用。

### 工具定义的两种方式

**方式 A：dataclass + 手写 JSON Schema（复杂参数用这个）**

```python
from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext


@dataclass
class MyTool(FunctionTool[AstrAgentContext]):
    name: str = "my_tool"
    description: str = "..."
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {...},
            "required": [...],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        return "..."
```

**方式 B：`@filter.llm_tool` 装饰器（简单参数）**

```python
@filter.llm_tool(name="get_weather")
async def get_weather(self, event: AstrMessageEvent, location: str) -> MessageEventResult:
    """获取天气信息。

    Args:
        location(string): 地点
    """
```

限制（`docs/zh/dev/star/guides/ai.md:115`）：

- 参数 schema **完全来自 docstring 的 `Args:` 段**，格式为 `参数名(类型): 描述`，不读函数签名类型注解。
- 缺 `Args:` 段或格式错误 → schema 为空 → LLM 传参被静默丢弃。
- **不支持** `parameters=` 显式传入，该写法被忽略。
- 支持类型：`string` / `number` / `object` / `boolean` / `array`，`array` 可写 `array[string]`。

结论：需要精确控制 schema 或参数多于两三个时，用方式 A。

### 工具在运行时的可达信息

`call()` 的 `context` 是 `ContextWrapper[AstrAgentContext]`：

| 表达式 | 内容 |
|---|---|
| `context.context.event` | 当前 `AstrMessageEvent`，可取 `unified_msg_origin`、`get_message_type()`、`get_sender_id()` |
| `context.context.context` | 插件 `Context`，可取配置、工具管理器、provider 等 |
| `context.messages` | 当前 LLM 上下文消息 |

工具注册是**全局的**，没有按会话注入的接口。要按会话控制，只能在 `call()` 内部判断 `event.unified_msg_origin` 并提前返回。

## 工具权限与可见性

`FuncToolManager.get_full_tool_set()`（`astrbot/core/provider/func_tool_manager.py:496`）会给所有非内置工具包一层 `_PermissionGuardedTool`：

- 每次调用都检查 WebUI 中该工具的权限配置。
- 插件工具会出现在 WebUI 工具页，用户可按工具启用/禁用（`active`）。
- 同名去重规则：`active=True` 优先；同状态时后加载者覆盖。

因此插件不需要自己实现工具级开关，只需把工具注册进去。

## 配置

插件目录下提供 `_conf_schema.json`，AstrBot 会：

1. 在 `data/config/<plugin_name>_config.json` 生成配置实体；
2. 实例化插件时把配置对象作为第二个参数传入 `__init__`；
3. 版本更新时按 Schema 递归补齐默认值、移除已删项。

Schema 条目字段（`docs/zh/dev/star/guides/plugin-config.md`）：

| 字段 | 说明 |
|---|---|
| `type` | **必填**：`string` / `text` / `int` / `float` / `bool` / `object` / `list` / `dict` / `template_list` / `file` |
| `description` | 一句话描述 |
| `hint` / `obvious_hint` | 问号悬浮提示 / 是否醒目 |
| `default` | 默认值 |
| `items` | `object` 的子 Schema |
| `invisible` | 面板隐藏 |
| `secret` | 仅遮罩显示，不加密、不改值 |
| `options` / `labels` / `subtitles` | 下拉选项 |
| `slider` | `int`/`float` 的 `{min,max,step}` |
| `_special` | 复用平台选择器：`select_provider`、`select_provider_tts`、`select_provider_stt`、`select_persona`、`select_knowledgebase` 等 |

`AstrBotConfig` 继承 `dict`，支持 `self.config.save_config()`。

## 依赖安装

- 第三方依赖写插件目录的 `requirements.txt`，安装插件时执行（`star_manager.py:355` 起）。
- 安装前有依赖预检与冲突检测，冲突会抛 `DependencyConflictError`。
- 官方约束（`docs/zh/dev/star/plugin-new.md:171`）：**不要用 `requests`**，用 `aiohttp`、`httpx` 等异步库。
- 优先选有预编译 wheel 的依赖，避免运行时编译。

## 数据与日志

- 持久化数据必须写 `data/` 目录，用 `astrbot.core.utils.path_utils.get_astrbot_data_path()` 取路径；不能写插件自身目录（更新/重装会覆盖）。
- 日志统一走 `astrbot.api.logger`。

## 代码规范

- `ruff format .` + `ruff check .`，提交前必须通过。
- 注释用英文（本项目约定见仓库 `AGENTS.md`）；docstring 用 Google 格式（`Args:` / `Returns:` / `Raises:`）。
- **借鉴其他项目的设计、功能创意或实现思路，必须在 README 说明来源并附链接；移植代码需遵守原项目协议并保留版权与许可声明**（`docs/zh/dev/star/plugin-new.md:172`）。

## 网络请求的既有约定

- 内置搜索工具用 `aiohttp.ClientSession(trust_env=True)`（`astrbot/core/tools/web_search_tools.py:234`），跟随系统代理。
- SSL 上下文用 `astrbot.core.utils.http_ssl` / `build_ssl_context_with_certifi` 提供的实现。
- 连接失败判定可复用 `astrbot/core/utils/network_utils.py` 的 `is_connection_error`。
