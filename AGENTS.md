<!-- 职责：项目级硬性约定与 agent 入口；不写具体功能设计与实现细节（见 docs/）。 -->

# 项目约定

## 前端必须使用 MVVM

Vue 前端**强制**遵循 MVVM。违反分层的代码不允许提交。

- **Model**：`webui/src/bridge.ts`，只负责与 AstrBot 视图桥接、HTTP 调用和类型定义
- **ViewModel**：`webui/src/viewmodels/use*.ts`，持有业务状态、调用 Model、暴露动作；用 `reactive` 返回给视图
- **View**：`webui/src/components/*.vue`，只接收 `vm`/`props` 并渲染，通过 `emit` 或调用 `vm` 的动作发起交互

**View 里禁止**：

- 直接 `import` 并调用 `bridge` 的请求函数
- 持有业务状态（表单以外的列表、加载态、错误态、领域数据）
- 写 `fetch` / `apiGet` / `apiPost` 逻辑

**View 里允许**：纯展示逻辑（展开/折叠、时间格式化）、i18n 文案。

新增功能模块时，一个模块对应：

```
modules/<name>/                 后端模块
webui/src/viewmodels/use<Name>.ts   ViewModel
webui/src/components/<Name>Panel.vue View
```

并在 `App.vue` 挂载。详细规则与示例见
[`docs/research/webui-mvvm.md`](docs/research/webui-mvvm.md)。

## 提交与版本号规范

### 版本号

1. 版本号只在 `metadata.yaml` 的 `version` 字段维护，不在 `main.py` 或其他地方重复写。
2. AstrBot 通过**仓库链接安装/更新**时，拉取默认分支并比较 `metadata.yaml` 的版本；**推送默认分支才生效**，GitHub Release 只是历史记录，不参与安装。
3. beta 期间 `metadata.yaml` 写预发布版本（如 `v0.3.0-beta.1`），正式版写成 `v0.3.0`。两者不能同号，否则 beta 阶段补的修复用户收不到。
4. 递增规则：bug 修复加补丁号；新增功能按语义化提升次版本。

### Commit

1. 改完先做基础检查：`python -m compileall modules main.py`（或等效命令）。
2. 看变更：`git status --short`、`git diff`。
3. 只提交本次相关文件，不要 `git add -A` 扫进无关文件。
4. 提交信息格式：`type(scope): 中文摘要`，type 用 `fix` / `feat` / `refactor` / `docs` / `chore`。
5. 发布提交前确认 `metadata.yaml` 已更新为目标版本。

### 分支

- **必须开分支**：新增功能、修复 bug、重构（会改变用户可观察行为）
  - `feat/<简短英文>`、`fix/<简短英文>`、`refactor/<简短英文>`
- **直接提交 `main`**：文档、注释、README、版本号递增、CI 配置、依赖调整、格式化、拼写修正
- 判断标准：这次改动会不会改变插件对用户的可观察行为。会 → 开分支；不会 → 直接 `main`
- 开发与自测在分支完成，验证通过后才合并回 `main`

### 完整维护流程

1. 从最新 `main` 切出 `fix/`、`feat/` 或 `refactor/` 分支，禁止直接改 `main`
2. 在分支上开发，同步递增 `metadata.yaml` 的 `version`
3. 本地门禁（三条都要过）：
   - `ruff check .`
   - `ruff format --check .`
   - `python -m pytest -q`
4. 推送分支
5. 发 beta：在分支上打预发布 tag（如 `v0.3.0-beta.1`）并推送；同时确保 `metadata.yaml` 是同一个预发布版本
6. 实测：装进实际 AstrBot 环境验证，**以用户反馈为准**，不拿自测替代
7. 发正式版：验证通过后合并分支到 `main`，把 `metadata.yaml` 改成正式版本（去掉 `-beta.N`），在 `main` 上打正式 tag 并推送
8. 清理已合并的功能分支

### 发布与安装

- 本仓库没有 CI/CD，推送前本地门禁必须通过
- 用户通过仓库链接安装/更新：AstrBot 拉默认分支、比较 `metadata.yaml` 版本，所以**推送 `main` 或让用户切到 beta 分支**才会更新
- GitHub Release / tag 只用于记录版本历史，不改变安装行为
- 未真正发布的版本号不要留在 `metadata.yaml`：tag 与 Release 删掉后，版本号要回退，否则下次发版用户版本号没变、收不到更新

### CHANGELOG

- `CHANGELOG.md` 每个基础版本一个小节（beta 与正式版共用同一篇）
- 发版前把未发布内容整理到对应版本小节；tag 版本、`metadata.yaml` 版本、CHANGELOG 小节三者保持一致

### 代码风格

- 门禁命令：`ruff check .` 与 `ruff format --check .`，配置见 `ruff.toml`
- 推送前必须本地跑通；修风格要真改代码，不得靠缩小 `select`、加 `ignore`、`# noqa` 绕过

