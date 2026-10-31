<!-- 职责：记录远程热补丁仓库的目录布局与清单格式，供补丁作者对照；不写插件实现细节与发布流程。 -->

# 热补丁仓库格式

插件「热补丁」视图从配置的 git 仓库拉取补丁，按仓库自带清单注入 AstrBot。清单字段的权威定义见
[`../superpowers/specs/2026-10-31-hotfix-loader-design.md`](../superpowers/specs/2026-10-31-hotfix-loader-design.md)，
本文只描述仓库应该长什么样。

## 目录布局

```
仓库根/
├── hotfix.json                 # 根清单，只声明格式版本
└── patches/
    ├── forward-content/
    │   ├── patch.json          # 补丁清单
    │   └── chain_parser.py     # 补丁模块
    └── another-fix/
        ├── patch.json
        └── ...
```

- 插件只扫描 `patches/` 下**一层**子目录，不递归
- 子目录必须有 `patch.json` 才视为补丁，没有的被忽略
- 补丁按目录名排序加载

## 根清单 `hotfix.json`

```json
{
  "schema": 1,
  "patches_dir": "patches"
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `schema` | 是 | 目前固定为 `1`，不认识的版本会被整体拒绝 |
| `patches_dir` | 否 | 补丁目录名，默认 `patches`；必须是单层目录名 |

## 补丁清单 `patch.json`

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

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | 否 | 缺省取目录名；全仓库唯一，重复时保留先出现的 |
| `description` | 否 | 展示在管理界面 |
| `file` | 是 | 相对补丁目录的 Python 文件，不能跳出该目录 |
| `astrbot` | 否 | PEP 440 版本范围；缺省不限制 |
| `import_as` | 否 | 补丁模块的导入名，通常不需要填 |
| `targets` | 是 | 非空数组，声明要替换的 `module.attribute` 与补丁模块里的 `source` 对象 |

## 生效规则

- 补丁**默认不启用**。用户在插件「热补丁」视图里勾选并应用后才注入
- 版本范围不匹配的补丁即使勾选也不会注入，界面显示「版本不匹配」
- 补丁模块可以引用目标包里的上游模块（例如 `from .image_refs import ...`），但同目录的辅助文件不会被自动加入模块搜索路径
- 上游修复后，应在视图里关闭对应补丁，或从仓库移除它的目录

## 示例

`AstrBot-hotfix` 仓库的 `forward-content` 补丁就是这个格式的完整实例：
根 `hotfix.json` + `patches/forward-content/{patch.json,chain_parser.py}`。
