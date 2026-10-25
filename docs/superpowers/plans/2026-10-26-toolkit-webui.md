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
- 前端不写配置、不渲染 Markdown、不引入外部 CDN（图标用本地打包的 lucide）
- 前端栈固定为 Vue 3 + Vite + Naive UI + TypeScript；构建产物提交到 `views/toolkit/`
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

### Task 3: 搭建 Vue 工程

**Files:**
- Create: `webui/package.json`
- Create: `webui/vite.config.ts`
- Create: `webui/tsconfig.json`
- Create: `webui/index.html`
- Create: `webui/src/main.ts`
- Create: `webui/src/App.vue`
- Modify: `.gitignore`

**Interfaces:**
- Produces: 可 `pnpm build` 的工程，产物落在 `views/toolkit/`

- [ ] **Step 1: 写 `webui/package.json`**

```json
{
  "name": "agent-toolkit-webui",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc --noEmit && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "@iconify-json/lucide": "^1.2.121",
    "@iconify/vue": "^5.0.1",
    "naive-ui": "^2.41.0",
    "vue": "^3.5.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.1.0",
    "typescript": "^5.6.0",
    "vite": "^6.0.0",
    "vue-tsc": "^2.1.0"
  }
}
```

- [ ] **Step 2: 写 `webui/vite.config.ts`**

```ts
import { resolve } from 'node:path'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: './',
  build: {
    outDir: resolve(__dirname, '../views/toolkit'),
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
        entryFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
  },
})
```

- [ ] **Step 3: 写 `webui/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "jsx": "preserve",
    "resolveJsonModule": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "noEmit": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "types": ["vite/client"]
  },
  "include": ["src/**/*.ts", "src/**/*.vue"]
}
```

- [ ] **Step 4: 写入口文件**

`webui/index.html`：

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Toolkit</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

`webui/src/main.ts`：创建 Vue 应用并挂载 `#app`。

`webui/src/App.vue`：先写一个只有标题的空壳，保证能构建。

- [ ] **Step 5: 更新 `.gitignore`**

追加：

```
webui/node_modules/
webui/dist/
```

`views/toolkit/` 是构建产物，必须提交，不要忽略。

- [ ] **Step 6: 安装依赖并构建**

Run: `cd webui && pnpm install`
Expected: 生成 `pnpm-lock.yaml`，无报错

Run: `pnpm build`
Expected: `views/toolkit/index.html` 与 `views/toolkit/assets/` 出现

- [ ] **Step 7: Commit**

```bash
git add webui/package.json webui/pnpm-lock.yaml webui/vite.config.ts webui/tsconfig.json webui/index.html webui/src/main.ts webui/src/App.vue .gitignore views/toolkit
git commit -m "feat: 搭建工具台 Vue 工程"
```

---

### Task 4: 实现 MVVM 组件并构建

**Files:**
- Create: `webui/src/bridge.ts`
- Create: `webui/src/i18n.ts`
- Create: `webui/src/components/ToolList.vue`
- Create: `webui/src/components/ToolDetail.vue`
- Create: `webui/src/components/TestBench.vue`
- Modify: `webui/src/App.vue`

**Interfaces:**
- Consumes: Task 2 的 `GET tools` / `POST tools/web_fetch/test`、Task 3 的工程
- Produces: 可用的工具台页面，构建产物在 `views/toolkit/`

- [ ] **Step 1: 写 `bridge.ts`（Model 层）**

导出以下类型与函数：

- `interface ToolInfo { name: string; active: boolean; description: string; parameters: Record<string, unknown> }`
- `interface FetchResult { ok: boolean; output: string; elapsed_ms: number; chars: number; truncated: boolean; final_url: string }`
- `const bridge = window.AstrBotPluginView`
- `async function ready(): Promise<void>`
- `function isDark(): boolean`
- `function locale(): string`
- `function t(key: string, fallback: string): string`（内部拼 `views.toolkit.${key}`）
- `function onContext(handler: () => void): void`
- `async function fetchTools(): Promise<ToolInfo[]>`
- `async function runFetch(payload: { url: string; max_chars: number; timeout: number }): Promise<FetchResult>`
- `async function copyText(text: string): Promise<void>`（`navigator.clipboard` 失败时用 `document.execCommand` fallback）

`window.AstrBotPluginView` 需要在文件顶部声明类型，避免 `vue-tsc` 报错。

- [ ] **Step 2: 写 `i18n.ts`**

封装 `t(key, fallback)`，提供 `useI18n()` 返回 `{ t, locale }`，语言变化时通过 `onContext` 触发重渲染（用 `ref` 存 `locale`）。

- [ ] **Step 3: 写 `ToolList.vue`**

- props：`tools: ToolInfo[]`、`selected: string`
- emits：`select(name: string)`
- 用 `NList` / `NListItem` 或原生按钮渲染；启用状态用 `NTag` 或小圆点
- 空列表时显示 `empty` 文案
- 窄屏下横向滚动（由父级 CSS 控制）

- [ ] **Step 4: 写 `ToolDetail.vue`**

- props：`tool: ToolInfo | null`
- 展示名称、状态徽标、描述
- 无工具时显示中等空状态

- [ ] **Step 5: 写 `TestBench.vue`**

- props：`tool: ToolInfo | null`
- 内部状态：`url`、`maxChars`、`timeout`、`loading`、`result`、`error`
- 使用 `NInput`、`NButton`、`NInputNumber`、`NAlert`
- 行为照 spec：Enter 触发、loading 禁点、`ok=false` 红字、请求失败保留上次结果、复制按钮 1.5s 反馈
- 结果区用 `<pre>`，等宽字体、`white-space: pre-wrap`、`max-height: 60vh`、`overflow: auto`

- [ ] **Step 6: 写 `App.vue`（ViewModel 层）**

- 用 `NConfigProvider` 包住页面，`:theme="isDark ? darkTheme : null"`，`:locale="zhCN"` / `enUS` 按 `locale()` 选择
- `NMessageProvider` 可选（如果 `TestBench` 用消息提示）
- 状态：`tools`、`selectedName`、`loadingTools`
- `onMounted` 调 `fetchTools()`，默认选中第一项
- `onContext` 时重新渲染文案
- 布局：顶部标题 + 工具数，左栏 `ToolList`，右栏 `ToolDetail` + `TestBench`
- 窄屏（<720px）用 CSS 媒体查询把两栏改纵向

- [ ] **Step 7: 构建与类型检查**

Run: `cd webui && pnpm build`
Expected: `vue-tsc --noEmit` 无错误，构建成功

Run: `ls ../views/toolkit`
Expected: `index.html` 与 `assets/`

- [ ] **Step 8: Commit**

```bash
git add webui/src views/toolkit
git commit -m "feat: 实现工具台 Vue 界面"
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
| 页面结构 | 3、4 |
| 测试台交互 | 4 |
| 视觉规范 | 3、4 |
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
| 主题切换 | Task 4 `NConfigProvider` + `onContext` |

**类型一致性**：`normalize_test_request` 返回 `(url, max_chars, timeout)`，Task 2 按此解包；`build_test_result(output, elapsed_ms)` 的两个参数在 Task 2 的调用顺序一致；`collect_tools(func_list, package_prefix)` 的参数顺序在 Task 1 测试与 Task 2 调用一致。
