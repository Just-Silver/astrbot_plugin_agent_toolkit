<!-- 职责：定义插件「远程热补丁加载器」的清单格式、配置、加载/注入/还原契约与验收标准；不写实现步骤、发布流程与具体补丁内容。 -->

# 远程热补丁加载器设计规格

日期：2026-10-31
状态：设计已确认，待实现

## 背景

AstrBot 的部分缺陷只能靠替换上游模块里的对象修复（例如 `chain_parser.OneBotPayloadParser` 的合并转发解析）。现有做法是把补丁文件单文件挂载进镜像，改一次要同步文件并重启容器，且无法按版本自动校验。

本插件新增一个可选的热补丁运行时：从配置的 GitHub 仓库拉取补丁，按仓库自带的清单注入到运行中的 AstrBot，并在插件卸载时还原。补丁的意义、内容与适用版本由补丁仓库自己维护，插件只做加载与注入。

## 目标

- 仓库地址、分支/标签可配置；仓库根提供清单，插件自动发现补丁
- 补丁在插件加载时生效，无需重启容器
- 版本不匹配、网络失败、清单非法、注入点缺失时降级，不影响插件其他功能
- 插件卸载或热重载时还原被替换的对象
- 下载内容持久化，离线可用

## 范围

**做**

- 配置分组 `hotfix`：`enabled` / `repo` / `ref`（在原生插件配置页编辑，WebUI 只读展示）
- 根清单 `hotfix.json` 与补丁清单 `patches/*/patch.json` 的解析与校验（schema、路径、版本、targets、目录发现）
- `git clone --depth 1` / `git fetch` 到插件数据目录，失败回退缓存
- 模块加载、按 targets 注入、记录原值、幂等 apply、逆序还原
- 补丁选择状态持久化；默认全部关闭，需在管理界面显式开启
- 独立管理视图 `hotfix`：来源信息、补丁列表、逐个开关、批量应用、展开详情
- 结构化日志：每个补丁的 applied / skipped / failed 及原因

**不做**

- 不在 WebUI 里修改仓库地址、`ref` 或总开关（配置页是唯一入口，后续再做）
- 不做签名校验、不校验补丁作者身份（信任配置的仓库）
- 不做定时轮询；只在插件加载、手动刷新和应用选择时更新
- 不支持私有仓库 token（将来需要时再加配置）
- 不替代官方升级流程；上游修复后应停用对应补丁

## 术语

| 术语 | 含义 |
|---|---|
| 补丁仓库 | 提供清单与补丁文件的远程 git 仓库 |
| 根清单 | 仓库根的 `hotfix.json`，只声明格式版本与全局约定，不列补丁 |
| 补丁清单 | `patches/<name>/patch.json`，声明单个补丁的文件、版本与 targets |
| 补丁模块 | 补丁清单 `file` 指向的 Python 文件，被当作模块加载 |
| target | 一次属性替换：把补丁模块的 `source` 赋给目标模块的 `attribute` |

## 目录结构

```
modules/
├── __init__.py
├── webfetch/       # 现有工具子包
└── hotfix/         # 本次新增子包（与 webfetch/ 平级，随插件分发）
    ├── __init__.py
    ├── models.py       # Manifest / PatchSpec / Target / AppliedPatch
    ├── manifest.py     # 清单读取、校验、路径与版本检查
    ├── repo.py         # git 命令封装、缓存目录、更新与回退
    ├── loader.py       # 补丁模块加载、注入、还原
    ├── selection.py    # 补丁选择状态读写
    ├── runtime.py      # apply / revert / refresh / 状态快照
    └── webapi.py       # 管理视图接口

views/
├── toolkit/        # 现有视图构建产物
└── hotfix/         # 新增：热补丁管理视图构建产物

webui/
├── index.html      # 现有：工具台入口
├── hotfix.html     # 新增：热补丁入口
└── src/            # 两个视图共享 bridge / i18n / ThemeShell

tests/
├── test_hotfix_manifest.py
├── test_hotfix_repo.py
├── test_hotfix_loader.py
├── test_hotfix_selection.py
├── test_hotfix_runtime.py
└── test_hotfix_webapi.py
```

`main.py` 新增：

```python
self._hotfix = HotfixRuntime(config=self.config, logger=logger)
self._hotfix.apply()
```

`terminate()` 中调用 `self._hotfix.revert()`。

## 配置

`_conf_schema.json` 新增：

```json
"hotfix": {
  "description": "远程热补丁",
  "type": "object",
  "items": {
    "enabled": {
      "description": "启用远程热补丁（从仓库拉取并注入）",
      "type": "bool",
      "default": false
    },
    "repo": {
      "description": "热补丁仓库地址，仅支持 https",
      "type": "string",
      "default": "https://github.com/Just-Silver/AstrBot-hotfix"
    },
    "ref": {
      "description": "分支、标签或提交；留空跟随默认分支",
      "type": "string",
      "default": ""
    }
  }
}
```

- `enabled=false` 或 `repo` 为空：完全不触碰 git、不加载补丁；管理视图仍可打开，但只展示缓存与「未启用」提示
- 读取用 `config.get("hotfix", {})`，缺字段按默认值处理（防止旧配置缺项）
- 这三个值只在原生插件配置页修改；管理视图只读展示，不写回配置

## 清单格式

仓库布局：

```
仓库根/
├── hotfix.json                 # 根清单：格式版本，不列具体补丁
└── patches/
    ├── forward-content/
    │   ├── patch.json          # 补丁清单
    │   └── chain_parser.py     # 补丁模块
    └── another-fix/
        ├── patch.json
        └── ...
```

### 根清单 `hotfix.json`

```json
{
  "schema": 1
}
```

| 字段 | 必填 | 规则 |
|---|---|---|
| `schema` | 是 | 整数，必须等于 `1`；不等则整份仓库拒绝加载 |

根清单不列补丁，补丁多了也不会让它膨胀。未知字段忽略。

### 补丁清单 `patches/<dir>/patch.json`

```json
{
  "name": "forward-content",
  "description": "引用合并转发时读不到转发正文",
  "file": "chain_parser.py",
  "astrbot": ">=4.29,<5",
  "targets": [
    {
      "module": "astrbot.core.utils.quoted_message.extractor",
      "attribute": "OneBotPayloadParser",
      "source": "OneBotPayloadParser"
    }
  ]
}
```

| 字段 | 必填 | 规则 |
|---|---|---|
| `name` | 否 | 缺省取目录名；非空字符串，全仓库唯一；重复时后加载者跳过并告警 |
| `description` | 否 | 字符串，仅用于日志 |
| `file` | 是 | 相对补丁目录的路径；拒绝绝对路径与 `..`，`resolve()` 后必须仍在补丁目录内 |
| `astrbot` | 否 | PEP 440 版本范围；缺省视为匹配；无法解析则跳过该补丁 |
| `import_as` | 否 | 补丁模块的导入名；缺省由 target 推导，见下节。`name` 中的非标识符字符替换为 `_` |
| `targets` | 是 | 非空数组，每个 target 必须有非空的 `module` / `attribute` / `source` |

未知字段一律忽略，保证清单可向前扩展。

补丁**默认不启用**，是否注入由管理界面的选择状态决定（见「选择状态」）。仓库无法通过清单强制某个补丁生效。

`target.attribute` 必须已存在于目标模块（本设计只做替换，不做新增）；不存在视为补丁与当前上游脱节，整补丁失败。

### 发现规则

- 只扫描仓库根 `patches/` 下的**一层**子目录，不递归、不扫描其他位置
- 子目录必须有 `patch.json` 才视为补丁；没有的被忽略，不报错
- 加载顺序按目录名排序，保证每次运行一致
- `patches/` 不存在或为空：视为没有补丁，不算错误

## 数据目录

```
<data>/plugin_data/astrbot_plugin_agent_toolkit/hotfix/
├── state.json                      # 选择状态，按 repo-slug 分组
└── <repo-slug>/                    # 补丁仓库缓存
    ├── .git/
    ├── hotfix.json
    └── patches/
```

- 根路径用 `get_astrbot_plugin_data_path()`，不硬编码绝对路径
- `repo-slug`：取仓库 URL 的 `owner/repo`，转小写，非 `[a-z0-9]` 字符替换为 `-`，例如 `https://github.com/Just-Silver/AstrBot-hotfix` → `just-silver_astrbot-hotfix`
- 同一仓库换 `ref` 复用同一目录，通过 fetch + reset 切换，不新增目录
- 选择状态与仓库缓存分开存放：删除缓存目录不会丢失用户的开关选择
- 不做自动清理；文档说明「删除 `<repo-slug>/` 即可强制重新下载」

选 `plugin_data` 而非 `data/temp` 的原因：这是跨重启可用的持久缓存，需要离线回退；`temp` 是可清理的临时区。也不能放插件安装目录，WebUI 更新插件会整目录覆盖。

## 选择状态

`state.json` 记录用户显式开启的补丁：

```json
{
  "repos": {
    "just-silver_astrbot-hotfix": {
      "selected": ["forward-content"],
      "last_commit": "3f9c1ab",
      "updated_at": "2026-10-31T14:22:00+08:00"
    }
  }
}
```

- 只记录选中的补丁名；不在列表里的补丁视为关闭
- 默认全部关闭：首次加载、新增补丁都需要用户在管理界面显式开启
- 状态按 `repo-slug` 分组，切换仓库不会丢掉原仓库的选择
- 仓库里暂时消失的补丁名保留在状态里，重新出现时恢复原选择
- 写入使用「读-改-写 + 临时文件替换」，避免半写文件
- 文件损坏或 JSON 非法：视为全部关闭，`warning`，不阻断加载

## 加载流程

```
apply():
  1. 校验配置：enabled、repo 为 https
  2. 更新仓库到本地缓存（失败则用现有缓存；无缓存则跳过全部）
  3. 读取并校验根清单 hotfix.json（失败则跳过全部）
  4. 读取选择状态（缺失时视为全部关闭）
  5. 扫描 patches/*/patch.json，按目录名排序，逐个补丁：
     a. 校验补丁清单、name 唯一性
     b. 未被选择的补丁标记 disabled，跳过（不再判断版本，也不加载）
     c. 已选择的补丁：版本不匹配标记 incompatible，跳过
     d. 加载补丁模块并注入；加载或注入失败标记 failed
  6. 输出汇总日志，并更新状态快照供管理界面读取
```

`apply()` 可重复调用：每次先 `revert()` 再重新执行，保证不叠加。

### 更新仓库

- 目录不存在：`git clone --depth 1 --single-branch <repo> <dir>`
  - `ref` 非空且不是完整提交 SHA 时追加 `--branch <ref>`
- 目录存在：`git -C <dir> fetch --depth 1 origin <ref>`，然后 `git -C <dir> reset --hard FETCH_HEAD`
  - `ref` 为空时执行 `git -C <dir> fetch --depth 1 origin`（clone 时的 `--single-branch` 已把远端限定为默认分支），再 reset 到 `FETCH_HEAD`
- `ref` 是完整提交 SHA（40 位十六进制）时：先确保仓库存在（必要时 clone 默认分支），再 `fetch --depth 1 origin <sha>` 后 reset
- 更新成功后读取 `git rev-parse HEAD`，只把前 7 位写进日志
- 子进程约束：超时 60 秒、`GIT_TERMINAL_PROMPT=0`、失败时不抛出到插件生命周期
- 进程内用一把锁串行化 git 操作

`apply()` 同步执行，只在插件 `__init__` 调用一次；最坏耗时受 git 超时约束（默认 60 秒）。不做后台异步更新。

### 版本校验

```python
from astrbot import __version__
from packaging.specifiers import SpecifierSet

if patch.astrbot and not SpecifierSet(patch.astrbot).contains(__version__, prereleases=True):
    # 跳过并告警
```

- `SpecifierSet` 解析异常：跳过该补丁，告警中带原始范围字符串
- AstrBot 版本读取失败：视为不匹配，跳过全部补丁并告警

## 注入与还原

### 模块加载

```python
spec = importlib.util.spec_from_file_location(import_as, file_path)
module = importlib.util.module_from_spec(spec)
sys.modules[import_as] = module
spec.loader.exec_module(module)
```

- `import_as` 缺省为「第一个 target 的 `module` 的父包 + `.hotfix_<name 规范化>`」，例如 `forward-content` + `astrbot.core.utils.quoted_message.extractor` → `astrbot.core.utils.quoted_message.hotfix_forward_content`
- 加载前先 `importlib.import_module(import_as.rpartition(".")[0])`，保证补丁文件的相对导入（如 `from .image_refs import ...`）能解析
- 加载失败：清理 `sys.modules` 中的条目，该补丁标记 failed

### 注入

对每个 target：

1. `target_module = importlib.import_module(target.module)`
2. `value = getattr(patch_module, target.source)`
3. `hasattr(target_module, target.attribute)` 为假：该补丁 failed 并回滚
4. 记录 `(target_module, target.attribute, 原值)`
5. `setattr(target_module, target.attribute, value)`

目标模块导入失败、`source` 不存在、`attribute` 不存在：该补丁 failed，回滚本补丁已注入的 target。

回滚规则：同一补丁内不允许「一半注入成功、一半失败」，宁可整个补丁不生效。

### 还原

- 按注入的逆序 `setattr` 回原值
- 移除补丁模块的 `sys.modules` 条目
- 单个属性还原失败只记录 warning，继续还原其余属性
- `revert()` 可重复调用，无副作用

## 管理界面

### 视图入口

- 独立视图 `hotfix`，与 `toolkit` 平级；AstrBot 通过插件根 `views/<name>/index.html` 发现
- 前端仍是同一个 `webui/` 工程，Vite 多入口：`index.html` → `views/toolkit/`，`hotfix.html` → `views/hotfix/`
- 共享 `bridge.ts`、`i18n.ts`、`ThemeShell.vue`；不引入路由与状态库
- i18n 写在 `.astrbot-plugin/i18n/<locale>.json` 的 `views.hotfix.*`，键缺失时前端回退到中文默认值

### 页面结构

```
热补丁                                              [刷新]
Just-Silver/AstrBot-hotfix · main · 3f9c1ab · 更新于 14:22
2 个补丁 · 1 个已应用 · 1 个待应用
[拉取失败：...                                              ×]

┌──────────────────────────────────────────────────────────┐
│ 补丁                      │ 适用版本   │ 状态     │ 启用 │
│ ▾ forward-content          │ >=4.29,<5 │ 已应用   │ 开   │
│   引用合并转发时读不到正文  │           │          │      │
│   ├ 目标：...extractor.OneBotPayloadParser              │
│   ├ 文件：patches/forward-content/chain_parser.py       │
│   └ 上次应用：2026-10-31 14:22 · 成功                    │
│ ▸ another-fix              │ >=5.0     │ 版本不匹配│ 关   │
│   当前 4.29.4，要求 >=5.0                                │
└──────────────────────────────────────────────────────────┘
                                   [放弃] [应用更改 (2)]
```

- 主行只显示：名称 + 描述、适用版本、状态、开关
- 点行展开：目标 `module.attribute`、文件路径、上次应用时间与结果
- 版本不匹配与失败原因以状态下方的小字展示，不额外占列
- 顶部来源行只读：仓库、`ref`、commit、更新时间；不提供编辑入口
- 顶部汇总：`N 个补丁 · M 个已应用 · K 个待应用`
- 底部只在有未保存改动时出现「放弃」与「应用更改（N）」

### 状态枚举

| 状态 | 含义 |
|---|---|
| `applied` | 已启用且注入成功 |
| `disabled` | 未启用（默认） |
| `incompatible` | 已启用，但当前 AstrBot 版本不匹配 |
| `failed` | 已启用，但加载或注入失败；`reason` 说明原因 |
| `pending` | 仅前端本地状态：勾选已改、尚未应用 |

状态判定按顺序短路：未选择 → `disabled`；已选择但版本不匹配 → `incompatible`；已选择但加载/注入失败 → `failed`；否则 `applied`。因此一个未启用且版本不匹配的补丁显示为 `disabled`，不会干扰用户的开关选择。

### 接口契约

接口前缀 `/{plugin_name}/hotfix`，用 `context.register_web_api` 注册，沿用现有视图的鉴权。

**`GET /{plugin_name}/hotfix/status`**

```json
{
  "enabled": true,
  "repo": "https://github.com/Just-Silver/AstrBot-hotfix",
  "ref": "",
  "commit": "3f9c1ab",
  "updated_at": "2026-10-31T14:22:00+08:00",
  "astrbot_version": "4.29.4",
  "patches": [
    {
      "name": "forward-content",
      "description": "引用合并转发时读不到转发正文",
      "file": "patches/forward-content/chain_parser.py",
      "astrbot": ">=4.29,<5",
      "targets": ["astrbot.core.utils.quoted_message.extractor.OneBotPayloadParser"],
      "selected": true,
      "state": "applied",
      "reason": "",
      "applied_at": "2026-10-31T14:22:00+08:00"
    }
  ],
  "error": ""
}
```

- `patches` 来自最近一次成功读取的清单缓存；从未成功时为空数组
- `error` 非空表示最近一次拉取/应用失败，前端显示提示条
- 未启用（`enabled=false`）时仍返回缓存清单，供用户查看
- 本接口只读本地状态与缓存，不触发 git 与注入

**`POST /{plugin_name}/hotfix/selection`**

```json
{"selected": ["forward-content"]}
```

- 只接受当前清单里存在的补丁名，未知名字忽略
- 保存状态 → `revert()` → `apply()`，使用最新缓存（不触发 git）
- 返回结构与 `GET /status` 相同
- 请求体不是对象、`selected` 不是字符串数组：400
- `enabled=false`：400，正文说明热补丁未启用

**`POST /{plugin_name}/hotfix/refresh`**

- 强制更新仓库（失败回退缓存）→ 重读清单 → 按现有选择 `revert()` + `apply()`
- 返回结构与 `GET /status` 相同；业务失败放在 `error`，不返回 500
- `enabled=false`：400，不触发 git

### 交互流程

1. 进入页面：`GET /status`，渲染来源、汇总与列表
2. 勾选变化：只改本地状态，行标记 `pending`，底部出现「应用更改（N）」
3. 「放弃」：丢弃本地勾选，恢复为后端返回的 `selected`
4. 「应用更改」：`POST /selection`，成功后用响应覆盖本地状态；期间禁用开关与按钮，显示加载态
5. 「刷新」：`POST /refresh`，成功后更新 commit 与列表；失败时保留原列表并显示提示条
6. `enabled=false`：整页提示「热补丁未启用，请在插件配置页开启」，开关与按钮禁用，仍展示缓存清单

### 前端组件

| 组件 | 职责 |
|---|---|
| `HotfixView.vue` | 页面容器：加载、错误条、汇总、保存/刷新动作 |
| `HotfixList.vue` | 补丁行、展开详情、开关 |
| `HotfixSummary.vue` | 计数汇总与待应用提示 |
| `bridge.ts` 扩展 | `getHotfixStatus()` / `applyHotfixSelection()` / `refreshHotfix()` |

## 失败处理

| 情况 | 行为 |
|---|---|
| 配置关闭 / repo 为空 | 不做任何事，不打印 hotfix 日志 |
| git 拉取失败，有缓存 | 使用缓存继续加载，`warning` 说明网络失败 |
| git 拉取失败，无缓存 | 跳过全部补丁，`warning` |
| `hotfix.json` 缺失或 JSON 非法 | 跳过全部补丁，`warning` |
| `schema` 不等于 1 | 跳过全部补丁，`warning` |
| `patches/` 不存在或为空 | 视为没有补丁，不告警 |
| 子目录没有 `patch.json` | 忽略该目录 |
| 单个 `patch.json` 非法（JSON/字段/路径穿越） | 跳过该补丁，其余补丁继续 |
| 补丁 `name` 重复 | 后加载的跳过并告警，先加载的保留 |
| 版本不匹配 | 跳过该补丁，`info` |
| 补丁模块 import 失败 | 该补丁 failed，其余继续 |
| target 导入失败 / source 不存在 / attribute 不存在 | 该补丁 failed 并回滚，其余继续 |
| 选择状态文件损坏或 JSON 非法 | 视为全部关闭，`warning` |
| `selection` 请求含未知补丁名 | 忽略未知名字，其余正常保存 |
| 应用选择时注入失败 | 返回 `status` 中该补丁 `failed` + `reason`，HTTP 仍为 200 |

任何情况下都不向插件生命周期抛异常，`web_fetch` 注册不受影响。

## 安全边界

- `repo` 只接受 `https://`，拒绝 `http://`、`file://`、`ssh://` 与其他协议
- 只把 `patches/*/patch.json` 声明的 `file` 作为入口执行；只扫描 `patches/` 一层，不递归、不扫描仓库其他目录
- 补丁清单 `file` 的 `resolve()` 结果必须在该补丁目录之内，防止路径穿越
- git 子进程不继承交互式凭据输入（`GIT_TERMINAL_PROMPT=0`）
- 注入目标模块必须可导入、`attribute` 必须已存在，否则整补丁失败，不静默造出新属性
- 注入行为会写 `info` 日志，包含补丁名、目标模块与属性名，便于审计

## 日志

固定前缀 `[hotfix]`，示例：

```
[hotfix] repo updated: just-silver_astrbot-hotfix @ 3f9c1ab
[hotfix] applied: forward-content -> astrbot.core.utils.quoted_message.extractor.OneBotPayloadParser
[hotfix] skipped: legacy-fix: astrbot 4.29.4 not in spec >=5.0
[hotfix] failed: broken-patch: target source 'X' not found in patch module
[hotfix] summary: 1 applied, 1 skipped, 1 failed
[hotfix] reverted: forward-content
```

不打印补丁文件内容，不打印任何凭据。

## 测试策略

全部用临时目录与假模块，不联网。

| 层 | 用例 |
|---|---|
| manifest | 根清单合法；`schema` 不符；根清单缺失/非法；子目录无 `patch.json` 被忽略；只扫一层不递归；补丁清单缺 `file`/`targets`；`file` 绝对路径与 `..` 穿越；`astrbot` 范围匹配/不匹配/无法解析；`name` 缺省取目录名；`name` 重复；未知字段被忽略 |
| repo | 目录不存在时执行 clone；存在时 fetch + reset；`ref` 为 SHA 的路径；git 失败时返回缓存状态；超时 |
| selection | 默认全部关闭；保存后读回一致；状态文件损坏视为全关；按 repo-slug 隔离；未知补丁名不写入 |
| loader | 正常注入生效；重复 apply 不叠加；单个 target 失败时整补丁回滚；`attribute` 不存在时整补丁回滚；`revert` 恢复原值；补丁模块 import 抛错时清理 `sys.modules`；未选择的补丁不加载 |
| runtime | 配置关闭时不调用 git；清单缺失时跳过；一个补丁失败不影响另一个；`terminate` 后目标恢复；`selection` 变更后只应用新选择 |
| webapi | `status` 字段完整；`selection` 归一化未知名字；非数组请求返回 400；业务失败走 `error` 而非 500；未启用时仍返回缓存清单 |

版本与 git 调用都用 monkeypatch 打桩；模块注入用 `types.ModuleType` 构造假目标模块。

## 验收标准

1. 默认配置下插件行为与现在完全一致，日志中不出现 `[hotfix]`，不产生任何 git 子进程
2. 配置合法仓库但未开启任何补丁时，不注入任何模块，管理界面中所有补丁为「未启用」
3. 在管理界面勾选并「应用更改」后，日志出现 `applied`，目标模块属性被替换，补丁状态变为「已应用」
4. 清单声明的 AstrBot 版本不匹配时，目标模块保持原样，日志出现 `skipped`，界面显示「版本不匹配」及当前版本
5. 断网且已有缓存时仍能应用补丁，日志说明使用了缓存
6. 断网且无缓存时插件正常加载，`web_fetch` 可用，管理界面显示错误提示条
7. 清单 `file` 含路径穿越时该补丁被拒绝，其他补丁仍可生效
8. 插件热重载或停用后，被替换的属性恢复原值
9. 同一配置连续两次 `apply()`，目标属性最终只被替换一次
10. 新增补丁只新建 `patches/<name>/` 并放入 `patch.json`，根 `hotfix.json` 无需改动
11. `patches/` 下没有 `patch.json` 的目录被忽略，不影响其他补丁
12. 管理视图可打开，来源行显示仓库、`ref`、commit 与更新时间；勾选变化后出现「应用更改（N）」，点「放弃」恢复原选择
13. 「刷新」更新 commit 与列表，已开启的补丁保持开启
14. `hotfix.enabled=false` 时管理视图仍可打开，显示「未启用」提示，开关与操作按钮禁用

## 跨仓库交付

本仓库实现加载器；补丁仓库需要按新布局整理：

```
AstrBot-hotfix/
├── hotfix.json                        # {"schema": 1}
└── patches/
    └── forward-content/
        ├── patch.json
        ├── chain_parser.py
        └── check-upstream.ps1
```

- 现有 `forward-content/` 移入 `patches/forward-content/`，并新增 `patch.json`
- 该仓库 README 补充「可被 astrbot_plugin_agent_toolkit 远程加载」的说明与清单字段表

清单格式以本规格为唯一事实源，补丁仓库只引用，不复制字段定义。

## 后续可选项

以下不在本次范围，记录避免遗忘：

- WebUI 里编辑仓库地址、`ref` 与总开关
- 私有仓库 token 配置
- 定时检查更新
- 清单签名校验
