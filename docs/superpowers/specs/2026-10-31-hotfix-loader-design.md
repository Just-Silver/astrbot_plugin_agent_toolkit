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

- 配置分组 `hotfix`：`enabled` / `repo` / `ref`
- 清单 `hotfix.json` 的解析与校验（schema、路径、版本、targets）
- `git clone --depth 1` / `git fetch` 到插件数据目录，失败回退缓存
- 模块加载、按 targets 注入、记录原值、幂等 apply、逆序还原
- 结构化日志：每个补丁的 applied / skipped / failed 及原因

**不做**

- 不提供 WebUI 管理界面
- 不做签名校验、不校验补丁作者身份（信任配置的仓库）
- 不做定时轮询；只在插件加载时更新
- 不支持私有仓库 token（将来需要时再加配置）
- 不替代官方升级流程；上游修复后应停用对应补丁

## 术语

| 术语 | 含义 |
|---|---|
| 补丁仓库 | 提供 `hotfix.json` 与补丁文件的远程 git 仓库 |
| 清单 | 仓库根目录的 `hotfix.json`，声明有哪些补丁、分别注入到哪里 |
| 补丁模块 | 清单 `file` 指向的 Python 文件，被当作模块加载 |
| target | 一次属性替换：把补丁模块的 `source` 赋给目标模块的 `attribute` |

## 目录结构

```
hotfix/
├── __init__.py     # 导出 HotfixRuntime
├── models.py       # Manifest / PatchSpec / Target / AppliedPatch
├── manifest.py     # 清单读取、校验、路径与版本检查
├── repo.py         # git 命令封装、缓存目录、更新与回退
└── loader.py       # 补丁模块加载、注入、还原

tests/
├── test_hotfix_manifest.py
├── test_hotfix_repo.py
├── test_hotfix_loader.py
└── test_hotfix_runtime.py
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

- `enabled=false` 或 `repo` 为空：完全不触碰 git、不加载补丁
- 读取用 `config.get("hotfix", {})`，缺字段按默认值处理（防止旧配置缺项）

## 清单格式

仓库根 `hotfix.json`：

```json
{
  "schema": 1,
  "patches": [
    {
      "name": "forward-content",
      "description": "引用合并转发时读不到转发正文",
      "file": "forward-content/chain_parser.py",
      "astrbot": ">=4.29,<5",
      "targets": [
        {
          "module": "astrbot.core.utils.quoted_message.extractor",
          "attribute": "OneBotPayloadParser",
          "source": "OneBotPayloadParser"
        }
      ]
    }
  ]
}
```

字段与校验：

| 字段 | 必填 | 规则 |
|---|---|---|
| `schema` | 是 | 整数，必须等于 `1`；不等则整份清单拒绝 |
| `patches` | 是 | 数组；为空表示没有补丁，不算错误 |
| `patches[].name` | 是 | 非空字符串，同清单内唯一 |
| `patches[].description` | 否 | 字符串，仅用于日志 |
| `patches[].file` | 是 | 仓库内相对路径；拒绝绝对路径与 `..`，`resolve()` 后必须仍在仓库根内 |
| `patches[].astrbot` | 否 | PEP 440 版本范围；缺省视为匹配；无法解析则跳过该补丁 |
| `patches[].enabled` | 否 | 布尔，默认 `true`；`false` 时跳过 |
| `patches[].import_as` | 否 | 补丁模块的导入名；缺省由 target 推导，见下节。`name` 中的非标识符字符替换为 `_` |
| `patches[].targets` | 是 | 非空数组，每个 target 必须有非空的 `module` / `attribute` / `source` |

未知字段一律忽略，保证清单可向前扩展。

`target.attribute` 必须已存在于目标模块（本设计只做替换，不做新增）；不存在视为补丁与当前上游脱节，整补丁失败。

## 数据目录

```
<data>/plugin_data/astrbot_plugin_agent_toolkit/hotfix/<repo-slug>/
├── .git/
├── hotfix.json
└── <补丁文件...>
```

- 根路径用 `get_astrbot_plugin_data_path()`，不硬编码绝对路径
- `repo-slug`：取仓库 URL 的 `owner/repo`，转小写，非 `[a-z0-9]` 字符替换为 `-`，例如 `https://github.com/Just-Silver/AstrBot-hotfix` → `just-silver_astrbot-hotfix`
- 同一仓库换 `ref` 复用同一目录，通过 fetch + reset 切换，不新增目录
- 不做自动清理；文档说明「删除该目录即可强制重新下载」

选 `plugin_data` 而非 `data/temp` 的原因：这是跨重启可用的持久缓存，需要离线回退；`temp` 是可清理的临时区。也不能放插件安装目录，WebUI 更新插件会整目录覆盖。

## 加载流程

```
apply():
  1. 校验配置：enabled、repo 为 https
  2. 更新仓库到本地缓存（失败则用现有缓存；无缓存则跳过全部）
  3. 读取并校验 hotfix.json（失败则跳过全部）
  4. 逐个补丁：
     a. enabled / astrbot 版本校验
     b. 加载补丁模块
     c. 依次注入 targets（任一失败则回滚该补丁已注入的部分，整补丁标记 failed）
  5. 输出汇总日志
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

## 失败处理

| 情况 | 行为 |
|---|---|
| 配置关闭 / repo 为空 | 不做任何事，不打印 hotfix 日志 |
| git 拉取失败，有缓存 | 使用缓存继续加载，`warning` 说明网络失败 |
| git 拉取失败，无缓存 | 跳过全部补丁，`warning` |
| `hotfix.json` 缺失或 JSON 非法 | 跳过全部补丁，`warning` |
| `schema` 不等于 1 | 跳过全部补丁，`warning` |
| 单个补丁清单非法（路径穿越等） | 跳过该补丁，其余补丁继续 |
| 版本不匹配 | 跳过该补丁，`info` |
| 补丁模块 import 失败 | 该补丁 failed，其余继续 |
| target 导入失败 / source 不存在 / attribute 不存在 | 该补丁 failed 并回滚，其余继续 |

任何情况下都不向插件生命周期抛异常，`web_fetch` 注册不受影响。

## 安全边界

- `repo` 只接受 `https://`，拒绝 `http://`、`file://`、`ssh://` 与其他协议
- 只把清单声明的 `file` 作为入口执行；补丁模块的相对导入限制在其所在目录，不额外扫描或执行仓库内其他脚本
- 清单 `file` 的 `resolve()` 结果必须在仓库根目录之内，防止路径穿越
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
| manifest | 合法清单；`schema` 不符；缺 `name`/`file`/`targets`；`file` 绝对路径与 `..` 穿越；`astrbot` 范围匹配/不匹配/无法解析；未知字段被忽略 |
| repo | 目录不存在时执行 clone；存在时 fetch + reset；`ref` 为 SHA 的路径；git 失败时返回缓存状态；超时 |
| loader | 正常注入生效；重复 apply 不叠加；单个 target 失败时整补丁回滚；`attribute` 不存在时整补丁回滚；`revert` 恢复原值；补丁模块 import 抛错时清理 `sys.modules` |
| runtime | 配置关闭时不调用 git；清单缺失时跳过；一个补丁失败不影响另一个；`terminate` 后目标恢复 |

版本与 git 调用都用 monkeypatch 打桩；模块注入用 `types.ModuleType` 构造假目标模块。

## 验收标准

1. 默认配置下插件行为与现在完全一致，日志中不出现 `[hotfix]`，不产生任何 git 子进程
2. 配置合法仓库后，日志出现 `applied`，目标模块属性被替换；引用合并转发解析使用补丁实现
3. 清单声明的 AstrBot 版本不匹配时，目标模块保持原样，日志出现 `skipped` 及原因
4. 断网且已有缓存时仍能应用补丁，日志说明使用了缓存
5. 断网且无缓存时插件正常加载，`web_fetch` 可用
6. 清单 `file` 含路径穿越时该补丁被拒绝，其他补丁仍可生效
7. 插件热重载或停用后，被替换的属性恢复原值
8. 同一配置连续两次 `apply()`，目标属性最终只被替换一次

## 跨仓库交付

本仓库实现加载器；补丁仓库需要新增根目录 `hotfix.json`：

- `AstrBot-hotfix` 根新增清单，声明 `forward-content` 补丁与它的 target
- 该仓库 README 补充「可被 astrbot_plugin_agent_toolkit 远程加载」的说明与清单字段表

清单格式以本规格为唯一事实源，补丁仓库只引用，不复制字段定义。

## 后续可选项

以下不在本次范围，记录避免遗忘：

- WebUI 里查看已应用补丁与版本
- 私有仓库 token 配置
- 定时检查更新
- 清单签名校验
