# 工具台 WebUI 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在插件详情页提供一个「工具台」视图，能列出插件注册的工具，并直接对 `web_fetch` 执行一次抓取看结果。

**Architecture:** 后端新增 `webfetch/webapi.py`，纯逻辑（参数归一化、工具列表过滤、结果组装）与平台 IO（`register_web_api` handler）分离，纯逻辑用 pytest 覆盖。前端是三个静态文件（`index.html` / `style.css` / `app.js`），通过 `window.AstrBotPluginView` bridge 调后端，无构建链。

**Tech Stack:** Python 3.10+、pytest、原生 HTML/CSS/JS、AstrBot plugin views + `astrbot.api.web`。

**Spec:** `docs/superpowers/specs/2026-10-26-toolkit-webui-design.md`

## Global Constraints

- 接口只有两个：`GET tools`、`POST tools/web_fetch/test`
- `output` 必须是 `run_fetch` 的原始返回值，不修改任何一个字符
- `max_chars` clamp 到 1000–50000，缺省 8000；`timeout` clamp 到 5–120，缺省 30
- 只保留 `handler_module_path` 以 `Main.__module__.rsplit(".", 1)[0]` 为前缀的工具
- 工具列表按 `name` 升序；没有工具时显示「当前没有注册任何工具」
- 前端不写配置、不渲染 Markdown、不引入外部 CDN/图标字体
- 颜色全部走 `--tk-*` CSS 变量，`[data-theme="dark"]` 覆盖
- 窄屏 <720px 时左栏折成顶部横向标签行
- 代码注释用英文，docstring 用 Google 格式；`ruff`（line-length 120，target py310）必须通过

## Review Focus

1. **非安全上下文复制**：WebUI 常用 `http://<ip>:6185` 访问，`navigator.clipboard` 在非 HTTPS 下不可用。期望复制按钮有 fallback，点了就真的复制成功。
2. **工具列表为空**：新装或工具被禁用时列表为空。期望右栏显示空状态，页面不报错、不白屏。
3. **接口返回 400**：URL 为空或参数异常时。期望页面显示「请求失败」，且上一次的结果不被清空。
4. **超长输出**：用户把 `max_chars` 调到 50000，结果区塞入 50KB 文本。期望页面可滚动、不横向溢出、不卡死。
5. **主题切换**：用户在 AstrBot 设置里切亮/暗。期望页面颜色立即跟随，没有写死的浅色块。

---

### Task 1: 后端纯逻辑与测试

**Files:**
- Create: `webfetch/webapi.py`
- Test: `tests/test_webapi.py`

**Interfaces:**
- Produces:
  - `DEFAULT_MAX_CHARS = 8000`、`DEFAULT_TIMEOUT = 30`、`MAX_CHARS_RANGE = (1000, 50000)`、`TIMEOUT_RANGE = (5, 120)`
  - `def clamp_int(value: object, low: int, high: int, default: int) -> int`
  - `def normalize_test_request(payload: dict) -> tuple[str, int, int] | None`
  - `def build_test_result(output: str, elapsed_ms: float) -> dict`
  - `def collect_tools(func_list, package_prefix: str) -> list[dict]`

- [ ] **Step 1: 写失败测试**

`tests/test_webapi.py`：

```python
import pytest

from webfetch.webapi import (
    DEFAULT_MAX_CHARS,
    DEFAULT_TIMEOUT,
    MAX_CHARS_RANGE,
    TIMEOUT_RANGE,
    build_test_result,
    clamp_int,
    collect_tools,
    normalize_test_request,
)


class FakeTool:
    def __init__(self, name, active=True, module="astrbot_plugin_agent_toolkit.webfetch.tool"):
        self.name = name
        self.active = active
        self.handler_module_path = module
        self.description = f"{name} tool"
        self.parameters = {"type": "object", "properties": {}}


def test_clamp_int_below_low():
    assert clamp_int(1, 1000, 50000, DEFAULT_MAX_CHARS) == 1000


def test_clamp_int_above_high():
    assert clamp_int(99999, 1000, 50000, DEFAULT_MAX_CHARS) == 50000


def test_clamp_int_non_numeric():
    assert clamp_int("abc", 5, 120, DEFAULT_TIMEOUT) == DEFAULT_TIMEOUT
    assert clamp_int(None, 5, 120, DEFAULT_TIMEOUT) == DEFAULT_TIMEOUT


def test_normalize_empty_url():
    assert normalize_test_request({"url": "   "}) is None
    assert normalize_test_request({}) is None


def test_normalize_defaults():
    assert normalize_test_request({"url": "https://example.com"}) == (
        "https://example.com",
        DEFAULT_MAX_CHARS,
        DEFAULT_TIMEOUT,
    )


def test_normalize_clamps_out_of_range():
    url, max_chars, timeout = normalize_test_request(
        {"url": "https://example.com", "max_chars": 999999, "timeout": 1}
    )
    assert max_chars == MAX_CHARS_RANGE[1]
    assert timeout == TIMEOUT_RANGE[0]


def test_build_test_result_normal():
    result = build_test_result("# Title\n\nbody\n\n---\nURL: https://example.com/", 420.4)
    assert result == {
        "ok": True,
        "output": "# Title\n\nbody\n\n---\nURL: https://example.com/",
        "elapsed_ms": 420,
        "chars": len("# Title\n\nbody\n\n---\nURL: https://example.com/"),
        "truncated": False,
        "final_url": "https://example.com/",
    }


def test_build_test_result_error_output():
    result = build_test_result("Error: HTTP 404.", 12)
    assert result["ok"] is False
    assert result["final_url"] == ""


def test_build_test_result_truncated():
    output = "body\n\n---\nURL: https://example.com/a\n[Content truncated: showed 50 of 156 characters.]"
    result = build_test_result(output, 30)
    assert result["truncated"] is True
    assert result["final_url"] == "https://example.com/a"


def test_collect_tools_filters_other_plugins():
    tools = [
        FakeTool("web_fetch"),
        FakeTool("other_tool", module="other_plugin.tool"),
        FakeTool("no_module", module=None),
    ]
    names = [tool["name"] for tool in collect_tools(tools, "astrbot_plugin_agent_toolkit")]
    assert names == ["web_fetch"]


def test_collect_tools_sorted_by_name():
    tools = [FakeTool("zeta"), FakeTool("alpha"), FakeTool("mid")]
    names = [tool["name"] for tool in collect_tools(tools, "astrbot_plugin_agent_toolkit")]
    assert names == ["alpha", "mid", "zeta"]


def test_collect_tools_maps_fields():
    tool = collect_tools([FakeTool("web_fetch")], "astrbot_plugin_agent_toolkit")[0]
    assert tool["active"] is True
    assert tool["description"] == "web_fetch tool"
    assert tool["parameters"] == {"type": "object", "properties": {}}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_webapi.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'webfetch.webapi'`

- [ ] **Step 3: 实现 `webfetch/webapi.py` 的纯逻辑部分**

本步骤只写常量与四个纯函数，**不要**导入任何 `astrbot` 模块，保证本地可测。

- `clamp_int`：`int(value)` 失败或 `None` 返回 `default`；结果 `max(low, min(high, parsed))`
- `normalize_test_request`：`url = str(payload.get("url") or "").strip()`，为空返回 `None`；`max_chars`/`timeout` 用 `clamp_int` 取值
- `build_test_result`：组装 spec 里的返回体；`final_url` 用 `re.search(r"^URL: (.+)$", output, re.MULTILINE)`，取 `group(1).strip()`，失败返回 `""`
- `collect_tools`：过滤 `str(getattr(tool, "handler_module_path", "") or "").startswith(package_prefix)`，映射 `name`/`active`/`description`/`parameters`，按 `name` 排序

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_webapi.py -q`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add webfetch/webapi.py tests/test_webapi.py
git commit -m "feat: 增加工具台 Web API 的纯逻辑与测试"
```

---

### Task 2: Web API handler 与路由注册

**Files:**
- Modify: `webfetch/webapi.py`
- Modify: `main.py`

**Interfaces:**
- Consumes: Task 1 的四个函数、`webfetch.service.run_fetch`
- Produces:
  - `async def list_tools(plugin: "Main") -> dict`
  - `async def test_web_fetch(plugin: "Main") -> dict`
  - `def register_routes(context, plugin: "Main", plugin_name: str) -> None`

handler 的请求/响应完全依赖 `astrbot.api.web`，本地无法导入，因此**不写单元测试**；它的正确性由 Task 5 的容器内验收覆盖。本任务只把请求解析、参数归一化、响应组装接到 Task 1 的纯函数上。

- [ ] **Step 1: 在 `webfetch/webapi.py` 追加 IO 层**

顶层不再导入 astrbot，改为在函数内导入：

```python
async def list_tools(plugin) -> dict:
    """Return the tools this plugin registered."""
    from astrbot.api.web import json_response

    package_prefix = plugin.__class__.__module__.rsplit(".", 1)[0]
    func_list = plugin.context.get_llm_tool_manager().func_list
    return json_response({"tools": collect_tools(func_list, package_prefix)})
```

```python
async def test_web_fetch(plugin) -> dict:
    """Run one fetch for the dashboard test bench."""
    import time

    from astrbot.api.web import error_response, json_response, request

    payload = await request.json(default={})
    normalized = normalize_test_request(payload if isinstance(payload, dict) else {})
    if normalized is None:
        return error_response("url is required", status_code=400)
    url, max_chars, timeout = normalized
    started = time.perf_counter()
    output = await run_fetch(url, max_chars=max_chars, timeout=timeout)
    return json_response(build_test_result(output, (time.perf_counter() - started) * 1000))
```

```python
def register_routes(context, plugin, plugin_name: str) -> None:
    """Register the toolkit view endpoints under the plugin prefix."""
    context.register_web_api(
        f"/{plugin_name}/tools",
        lambda: list_tools(plugin),
        ["GET"],
        "List plugin tools",
    )
    context.register_web_api(
        f"/{plugin_name}/tools/web_fetch/test",
        lambda: test_web_fetch(plugin),
        ["POST"],
        "Run one web_fetch call",
    )
```

如果 AstrBot 的 handler 不接受 lambda（需要可 await 的函数），改成 `functools.partial` 或模块级函数加闭包——以实际注册成功为准，保持签名可调用即可。

- [ ] **Step 2: 在 `main.py` 注册路由**

在 `__init__` 末尾（`enabled` 判断之后、`add_llm_tools` 之后）加入：

```python
from .webfetch.webapi import register_routes

register_routes(self.context, self, "astrbot_plugin_agent_toolkit")
```

即使 `enabled=false` 也应注册视图（页面要能显示"没有工具"），所以 `register_routes` 放在 `enabled` 判断之前。

- [ ] **Step 3: 语法与导入检查**

Run: `python -m py_compile main.py webfetch/webapi.py`
Expected: 无输出（编译通过）

Run: `python -m pytest -q`
Expected: 全部 PASS（Task 1 的测试仍然通过）

- [ ] **Step 4: Commit**

```bash
git add webfetch/webapi.py main.py
git commit -m "feat: 注册工具台 Web API 路由"
```

---

### Task 3: 视图骨架与样式

**Files:**
- Create: `views/toolkit/index.html`
- Create: `views/toolkit/style.css`

**Interfaces:**
- Produces: 固定 DOM id，供 Task 4 的 `app.js` 使用
  - `#tool-count`、`#tool-list`、`#tool-name`、`#tool-status`、`#tool-desc`
  - `#url-input`、`#fetch-btn`、`#max-chars`、`#timeout`
  - `#meta`、`#output`、`#copy-btn`、`#error-line`

- [ ] **Step 1: 写 `index.html`**

结构（顺序固定，class 名可调整，id 必须一致）：

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Toolkit</title>
    <link rel="stylesheet" href="./style.css" />
  </head>
  <body>
    <div class="tk">
      <header class="tk-top">
        <span class="tk-title" id="heading">Agent Toolkit</span>
        <span class="tk-count" id="tool-count"></span>
      </header>
      <div class="tk-main">
        <aside class="tk-side">
          <div class="tk-side-label" id="tools-label">工具</div>
          <nav id="tool-list"></nav>
        </aside>
        <section class="tk-content">
          <div class="tk-head">
            <span class="tk-name" id="tool-name"></span>
            <span class="tk-badge" id="tool-status"></span>
          </div>
          <p class="tk-desc" id="tool-desc"></p>
          <div class="tk-row">
            <input class="tk-input" id="url-input" placeholder="https://example.com" />
            <button class="tk-btn" id="fetch-btn">抓取</button>
          </div>
          <div class="tk-adv">
            <label>字符上限 <input id="max-chars" value="8000" /></label>
            <label>超时 <input id="timeout" value="30" /> 秒</label>
            <span class="tk-fade" id="only-once">仅本次测试生效</span>
          </div>
          <div class="tk-meta" id="meta"></div>
          <p class="tk-error" id="error-line" hidden></p>
          <pre class="tk-out" id="output"></pre>
          <button class="tk-ghost" id="copy-btn">复制</button>
        </section>
      </div>
    </div>
    <script type="module" src="./app.js"></script>
  </body>
</html>
```

- [ ] **Step 2: 写 `style.css`**

必须包含：

- `:root` 与 `[data-theme="dark"]` 两套 `--tk-*` 变量（值照抄 spec 的视觉规范）
- 外层 14px 圆角、控件 8px 圆角
- `.tk-out` 等宽字体、`line-height: 1.65`、`white-space: pre-wrap`、`overflow: auto`、`max-height: 60vh`
- `.tk-error` 用错误色
- `@media (max-width: 720px)`：`.tk-main` 改 `flex-direction: column`，`.tk-side` 变横向滚动
- 不出现任何硬编码主题色（除错误色），其余全部 `var(--tk-*)`

- [ ] **Step 3: 检查文件存在与关键 id**

Run: `python -c "from pathlib import Path; h=Path('views/toolkit/index.html').read_text(encoding='utf-8'); ids=['tool-list','url-input','fetch-btn','max-chars','timeout','meta','output','copy-btn','error-line']; missing=[i for i in ids if f'id=\"{i}\"' not in h]; print('missing:', missing)"`
Expected: `missing: []`

- [ ] **Step 4: Commit**

```bash
git add views/toolkit/index.html views/toolkit/style.css
git commit -m "feat: 增加工具台视图骨架与样式"
```

---

### Task 4: 前端交互逻辑

**Files:**
- Create: `views/toolkit/app.js`

**Interfaces:**
- Consumes: Task 3 的 DOM id、Task 2 的 `GET tools` / `POST tools/web_fetch/test`、`window.AstrBotPluginView`
- Produces: 可用的工具台页面

- [ ] **Step 1: 写 `app.js`**

必须实现的行为：

1. `const bridge = window.AstrBotPluginView; const ctx = await bridge.ready();`
2. `const tools = (await bridge.apiGet("tools")).tools;` 渲染 `#tool-list`，每项 `<button class="tk-item">`，`data-name` 存工具名，选中项加 `.on`；`#tool-count` 显示 `N 个工具 · M 个已启用`
3. 列表为空：`#tool-name` 显示 `empty` 文案，隐藏输入区与结果区
4. 选中工具：更新 `#tool-name`、`#tool-status`、`#tool-desc`；没有测试能力的工具只显示详情
5. 抓取：`url = input.value.trim()`，为空直接返回；`#fetch-btn` 置 `disabled` 与 loading 文案；`await bridge.apiPost("tools/web_fetch/test", {url, max_chars, timeout})`
6. 成功：`#meta` 显示 `${elapsed_ms}ms · ${chars} 字符 · ${truncated ? '已截断' : '未截断'} · ${final_url || '—'}`；`#output.textContent = result.output`；`ok=false` 时给 `#output` 加错误 class
7. 失败（catch）：`#error-line` 显示「请求失败」，**不清空** `#output`
8. 复制：优先 `navigator.clipboard.writeText`，不可用时 fallback 到临时 `textarea` + `document.execCommand("copy")`；成功后按钮文案变 `copied` 并在 1.5s 后恢复
9. Enter 在 `#url-input` 内触发抓取
10. `bridge.onContext(render)`：语言切换时重渲染文案；`bridge.t("views.toolkit.<key>", fallback)` 取值

- [ ] **Step 2: 语法检查**

Run: `node --check views/toolkit/app.js`
Expected: 无输出。如果环境没有 node，跳过并在 Task 5 的容器验收里覆盖。

- [ ] **Step 3: Commit**

```bash
git add views/toolkit/app.js
git commit -m "feat: 实现工具台前端交互"
```

---

### Task 5: 国际化、文档与验收

**Files:**
- Create: `.astrbot-plugin/i18n/zh-CN.json`
- Create: `.astrbot-plugin/i18n/en-US.json`
- Modify: `README.md`
- Modify: `metadata.yaml`

- [ ] **Step 1: 写 i18n 文件**

`zh-CN.json`：

```json
{
  "views": {
    "toolkit": {
      "title": "工具台",
      "description": "查看插件提供的工具并直接测试",
      "heading": "Agent Toolkit",
      "tools": "工具",
      "enabled": "已启用",
      "disabled": "已禁用",
      "fetch": "抓取",
      "fetching": "抓取中…",
      "max_chars": "字符上限",
      "timeout": "超时",
      "seconds": "秒",
      "elapsed": "耗时",
      "chars": "字符",
      "truncated": "已截断",
      "not_truncated": "未截断",
      "copy": "复制",
      "copied": "已复制",
      "empty": "当前没有注册任何工具",
      "only_once": "仅本次测试生效",
      "request_failed": "请求失败"
    }
  }
}
```

`en-US.json` 提供同结构英文文案。

- [ ] **Step 2: 更新 README**

加一节「WebUI 工具台」，说明入口（插件详情页 → 工具台）、能做什么、不做什么（不改配置、不留历史）。同时把版本号相关说明更新到 `v0.2.0`。

- [ ] **Step 3: 更新 `metadata.yaml` 版本**

`version: v0.2.0`（新增视图属于功能版本）。

- [ ] **Step 4: 静态检查与全量测试**

Run: `ruff format . && ruff check . && python -m pytest -q`
Expected: `All checks passed!`，测试全绿。

- [ ] **Step 5: 容器内验收**

在 AstrBot 容器里重载插件，然后：

| 步骤 | 期望 |
|---|---|
| 插件详情页 → 工具台 | 页面打开，左栏出现 `web_fetch` |
| 输入 `https://example.com` 点抓取 | 结果与命令行 `run_fetch` 一致 |
| 输入 `http://127.0.0.1:6185/` | 红字 `Error: refusing to fetch...` |
| 字符上限改 50 | 结果被截断，提示 50/N |
| 点复制 | 按钮变「已复制」，粘贴内容正确 |
| 切亮/暗主题 | 颜色跟随 |
| 窗口缩到 720px 以下 | 左栏折成顶部标签行 |
| 切 English | 文案变英文 |

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: 补齐工具台国际化与文档"
```

---

## Self-Review

**Spec 覆盖**

| spec 章节 | 任务 |
|---|---|
| 目录结构 | 1–5 |
| GET tools | 1（纯逻辑）、2（路由） |
| POST test | 1（纯逻辑）、2（路由） |
| 返回体字段 | 1 `build_test_result` |
| 页面结构 | 3 |
| 测试台交互 | 4 |
| 视觉规范 | 3 |
| 国际化 | 5 |
| 错误处理 | 4（前端）、2（400 响应） |
| 安全 | 2（固定 endpoint）、1（clamp） |
| 测试 | 1（单元）、5（手工） |
| 验收标准 | 5 |

**Review Focus 对应**

| 风险 | 处理位置 |
|---|---|
| 非安全上下文复制 | Task 4 第 8 条 fallback，Task 5 验收 |
| 工具列表为空 | Task 4 第 3 条，Task 5 验收 |
| 400 保留上次结果 | Task 4 第 7 条 |
| 超长输出 | Task 3 `.tk-out` 的 `overflow` 与 `max-height` |
| 主题切换 | Task 3 CSS 变量 + Task 4 `onContext` |

**类型一致性**：`normalize_test_request` 返回 `(url, max_chars, timeout)`，Task 2 按此解包；`build_test_result(output, elapsed_ms)` 的两个参数在 Task 2 的调用顺序一致；`collect_tools(func_list, package_prefix)` 的参数顺序在 Task 1 测试与 Task 2 调用一致。
