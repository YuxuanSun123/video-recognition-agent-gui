# 视频识别 Agent GUI

一个面向影视拉片、视频审阅和多模态分析的原生桌面工具。它可以调用阿里云百炼 / DashScope 的 Qwen 视频理解和音频专精模型，把视频分析成逐镜报告，并导出 Markdown 或 CSV。

当前主入口是原生 Windows GUI，不是浏览器页面或 HTML 外壳。

## 功能特性

- 原生 Tkinter 桌面工作台：左侧配置任务，右侧查看逐镜表格和镜头详情。
- 支持阿里云百炼 / DashScope API Key 本地保存。
- 支持本地视频路径分析：走 DashScope Python SDK，单个视频不超过 100MB。
- 支持公网 URL 分析：走 OpenAI 兼容接口的 `video_url`。
- 支持 GitHub Releases 上传：把本地视频上传为 Release asset，并用 `browser_download_url` 作为临时公网 URL。
- 支持两种分析模式：
  - 视频理解主力：默认使用 `qwen3.7-plus`，适合逐镜拉片、长视频理解、结构化报告。
  - 声音/对白专精：默认使用 `qwen3.5-omni-plus`，适合对白、音乐、环境声更重要的场景。
- 支持手动选择抽帧 fps：`0.2`、`0.5`、`1`、`2`。
- 支持粘贴字幕 / ASR 文本和补充分析要求。
- 支持导出 Markdown 和 CSV。

## 项目结构

```text
.
├── desktop_app.py           # 原生桌面 GUI
├── video_agent_core.py      # 配置、API 调用、上传、解析、导出核心逻辑
├── start_gui.cmd            # Windows 双击启动脚本
├── requirements.txt         # Python 依赖
├── server.mjs               # 旧版本地网页服务，保留作备用
├── public/                  # 旧版网页界面
└── scripts/                 # DashScope 本地路径辅助脚本
```

## 安装

需要 Windows + Python 3.10 或更新版本。

```powershell
py -m pip install -r requirements.txt
```

Tkinter 是 Windows Python 通常自带的标准 GUI 库，不需要额外安装。

## 启动

方式一，双击：

```text
start_gui.cmd
```

方式二，命令行启动：

```powershell
py desktop_app.py
```

## 配置

可以在 GUI 的「设置与密钥」页保存，也可以手动创建 `.env`：

```env
DASHSCOPE_API_KEY=sk-your-api-key
DASHSCOPE_WORKSPACE_ID=你的业务空间ID
DASHSCOPE_REGION=cn-beijing
DASHSCOPE_BASE_URL=
ALIYUN_VISION_MODEL=qwen3.7-plus
ALIYUN_OMNI_MODEL=qwen3.5-omni-plus
GITHUB_TOKEN=
GITHUB_OWNER=
GITHUB_REPO=
GITHUB_RELEASE_TAG=video-agent-temp
GITHUB_RELEASE_NAME=Video Agent Temporary Uploads
GITHUB_ASSET_PREFIX=video-agent
```

如果已经知道完整百炼 OpenAI 兼容接口地址，也可以直接设置：

```env
DASHSCOPE_BASE_URL=https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
```

`.env` 已被 `.gitignore` 忽略，不会提交到仓库。

## 视频输入方式

### 本地路径

上传方式选择 `local`。平台会通过 DashScope Python SDK 使用本地 `file://` 路径调用模型。

适合小文件测试，视频本身不超过 100MB。

### GitHub Releases 临时 URL

上传方式选择 `github`。平台会先把本地视频上传到指定仓库的 Release asset，再把返回的 `browser_download_url` 交给模型分析。

注意：

- 仓库建议 public，否则模型服务通常无法读取下载 URL。
- GitHub Token 需要具备对应仓库的 release 写入权限。
- 这适合作为临时公网 URL 方案，不建议长期托管大批量视频。

### 公网 URL

上传方式选择 `url`，直接粘贴模型服务能访问的视频地址。

## 阿里云视频限制提醒

根据阿里云百炼视觉理解文档：

- 以公网 URL 传入时，`qwen3.6` 系列、`qwen3.5` 系列、Qwen3-VL 系列等最高可到 2GB，具体以官方文档和模型版本为准。
- 以 Base64 传入时，编码后的字符串需要小于 10MB。
- 以本地文件路径传入时，视频本身不超过 100MB，并且主要适用于 DashScope Python / Java SDK。
- 默认建议用 `qwen3.7-plus` 生成逐镜拉片主报告；对白、音乐、环境声很关键时，切换到 `qwen3.5-omni-plus` 做声音专精分析或交叉校对。

参考：

- https://help.aliyun.com/zh/model-studio/vision
- https://help.aliyun.com/zh/model-studio/qwen-omni

## 旧版网页入口

旧版网页平台仍保留：

```powershell
npm install
npm start
```

然后打开：

```text
http://localhost:5177
```

当前推荐使用 `desktop_app.py` 或 `start_gui.cmd` 启动原生 GUI。

## 安全说明

- 不要提交 `.env`。
- 不要把真实 API Key 写进 README、截图或 issue。
- 如果用 GitHub Releases 作为视频临时 URL，确认视频内容适合公开访问。
