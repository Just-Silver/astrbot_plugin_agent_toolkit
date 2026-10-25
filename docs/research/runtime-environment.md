<!-- 职责：记录本插件的部署形态与运行环境事实（Docker 基础镜像、依赖安装路径、网络与代理）；不写 AstrBot 插件 API 约束。 -->

# 运行环境

## 部署形态

用户以 **Docker** 部署 AstrBot，插件通过仓库链接安装到容器内。

## 官方镜像事实

`upstream/AstrBot/Dockerfile`：

- 基础镜像：`python:3.12-slim`
- 工作目录：`/AstrBot`
- 已预装系统包：`gcc`、`build-essential`、`python3-dev`、`libffi-dev`、`libssl-dev`、`ca-certificates`、`ffmpeg`、`libavcodec-extra`、`fonts-noto-cjk`、`curl`、`gnupg`、`git`、`ripgrep`、`nodejs`
- 依赖管理：容器内用 `uv` 安装并 `uv pip install --system`

由此得到的约束：

1. **没有预装 `libxml2-dev` / `libxslt-dev`**。依赖如果缺少 manylinux wheel、需要从源码编译 `lxml`，安装会失败。
2. 有 `gcc`/`python3-dev`，纯 Python 扩展的编译不受影响。
3. 容器内无 GUI、无浏览器，抓取只能走 HTTP。

## 插件依赖安装

AstrBot 在安装/加载插件时读取插件目录的 `requirements.txt`，经依赖预检后安装（`astrbot/core/star/star_manager.py:355`）。依赖装进系统 Python 环境，不是插件私有 venv。

影响：

- 依赖冲突会影响整个 AstrBot 进程，选依赖时优先考虑体积小、wheel 覆盖广的库。
- 安装失败会阻断插件加载，需在 README 给出排查提示。

## 网络与代理

- 容器通常直连，需依赖宿主或容器自身的代理配置。
- AstrBot 内置请求约定用 `trust_env=True`，即跟随 `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY` 环境变量；插件应保持一致。
- 出站访问是网页抓取的正常需求，但**入站方向的私网地址必须拦截**：容器网络里 `127.0.0.1`、`172.16.0.0/12`、`host.docker.internal` 都可能指向 AstrBot 自身或其他服务。

## 验证方式

本机无法直接模拟容器环境时，以下检查可以提前暴露大部分问题：

- 依赖能否在 `python:3.12-slim` 下用 `pip install` 一次装成功（重点看是否需要编译）。
- 抓取实现是否只依赖标准库以外的声明依赖。
- 代理环境变量存在/不存在时行为是否一致。
