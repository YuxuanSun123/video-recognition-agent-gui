# Shot Reader / 视频识别 Agent GUI

Shot Reader 是一个面向影视拉片、逐镜分析和多模态视频审阅的桌面工具。它把视频、字幕和补充要求交给阿里云百炼 / DashScope 模型，生成带截图、镜号、时间码、景别、镜头运动、画面内容、声音音乐和分析注释的逐镜报告，并支持导出 Markdown 与 CSV。

当前主版本采用 `Tauri + React/Vite + Python FastAPI sidecar`：

- `React/Vite` 负责套印报告风格界面、抽屉切换、报告库、提示词和设置页。
- `Tauri` 负责桌面窗口、打包、系统级启动和跨平台安装包。
- `FastAPI sidecar` 负责本地配置、DashScope 调用、GitHub Releases 临时上传、缩略图生成和导出。

## 功能亮点

- 逐镜拉片表格：截图、镜号、时间码、景别、镜头运动、画面内容、声音音乐、分析注释。
- 双层抽屉工作区：输入设置和逐镜结果在同一区域滑动切换。
- 支持三种视频输入：本地路径、公网 URL、GitHub Releases 临时 URL。
- 支持本地路径模式：通过 DashScope SDK 传入本地视频文件，单文件建议不超过 100MB。
- 支持公网 URL 模式：适合较大视频，由模型服务直接读取可访问 URL。
- 支持 GitHub Releases 上传：把本地视频临时上传为公开下载地址，再交给模型分析。
- 默认模型：
  - `qwen3.7-plus`：视频理解主力，适合视觉叙事、逐镜结构化报告。
  - `qwen3.5-omni-plus`：声音/对白专精，适合对白、音乐、环境声更重要的场景。
- 支持抽帧 fps：`0.2`、`0.5`、`1`、`2`。
- 支持字幕/ASR 文本和补充分析要求。
- 支持导出 Markdown 与 CSV。
- API Key 和上传配置只保存在本机 `.env` 或应用数据目录，不会写入 Release 包。

## 下载使用

在 GitHub Releases 页面下载对应系统版本：

- Windows：下载 `Shot-Reader-Windows-Portable-v0.2.0.zip` 或安装包，解压后运行 `Shot Reader.exe`。
- macOS：下载 macOS 版本资产后打开应用。未签名版本首次启动可能需要右键应用选择“打开”。

首次启动后，进入“设置与密钥”保存 DashScope API Key、工作空间信息和可选 GitHub 上传配置。

## 配置

可以在应用设置页保存，也可以在项目根目录创建 `.env`：

```env
DASHSCOPE_API_KEY=sk-your-api-key
DASHSCOPE_BASE_URL=
DASHSCOPE_WORKSPACE_ID=
DASHSCOPE_REGION=cn-beijing

ALIYUN_VISION_MODEL=qwen3.7-plus
ALIYUN_OMNI_MODEL=qwen3.5-omni-plus

GITHUB_TOKEN=
GITHUB_OWNER=
GITHUB_REPO=
GITHUB_RELEASE_TAG=video-agent-temp
GITHUB_RELEASE_NAME=Video Agent Temporary Uploads
GITHUB_ASSET_PREFIX=video-agent
```

如果你已经知道完整的百炼 OpenAI 兼容接口地址，也可以直接设置：

```env
DASHSCOPE_BASE_URL=https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
```

`.env` 已在 `.gitignore` 中忽略，不会被提交到仓库。

## 视频输入方式

### 本地路径

上传方式选择“本地路径”。平台会通过 DashScope SDK 使用本地文件路径调用模型。这个模式适合小文件和本地测试，视频本身建议不超过 100MB。

### 公网 URL

上传方式选择“公网 URL”，直接粘贴模型服务可访问的视频地址。这个方式更适合较大视频。视频大小限制以阿里云百炼对应模型文档为准。

### GitHub Releases 临时 URL

上传方式选择“上传 GitHub”。平台会先把本地视频上传到指定仓库的 Release asset，再把返回的 `browser_download_url` 交给模型分析。

注意：

- 仓库建议设为 public，否则模型服务通常无法读取下载地址。
- GitHub Token 需要具备对应仓库的 Release 写入权限。
- 这个方案适合临时公网 URL，不建议长期托管大量或敏感视频。

## 开发环境

需要：

- Node.js LTS
- Python 3.10+
- Rust stable
- Tauri v2 所需系统依赖

安装依赖：

```powershell
npm install
py -m pip install -r requirements.txt
```

macOS / Linux 可以使用：

```bash
npm install
python3 -m pip install -r requirements.txt
```

启动 Web 开发模式：

```powershell
npm run dev
```

启动 Tauri 桌面开发模式：

```powershell
npm run tauri:dev
```

构建桌面包：

```powershell
npm run tauri:build
```

Windows 构建产物通常位于：

```text
src-tauri/target/release/bundle/nsis/
src-tauri/target/release/bundle/msi/
```

macOS 构建产物通常位于：

```text
src-tauri/target/release/bundle/dmg/
src-tauri/target/release/bundle/macos/
```

## Release 流程

仓库包含 GitHub Actions 发布工作流：`.github/workflows/release.yml`。

发布新版本：

```powershell
git tag v0.2.0
git push origin v0.2.0
```

工作流会在 GitHub runner 上分别构建：

- Windows x64 安装包
- macOS runner-native 应用包

Tauri sidecar 会在构建时自动打包为当前平台需要的 `backend-sidecar-$TARGET_TRIPLE` 二进制文件。Tauri 官方要求 sidecar 文件名包含目标平台 triple，例如 Windows 的 `x86_64-pc-windows-msvc` 或 Apple Silicon macOS 的 `aarch64-apple-darwin`。

## 项目结构

```text
.
├── src/                      # React / Vite 工作台
├── src-tauri/                # Tauri 桌面壳
├── backend_api.py            # FastAPI 本地 sidecar
├── video_agent_core.py       # 配置、上传、DashScope 调用、解析和导出
├── scripts/                  # sidecar 构建脚本
├── requirements.txt          # Python 依赖
├── package.json              # 前端与 Tauri 脚本
└── .github/workflows/        # GitHub Release 构建工作流
```

## 安全说明

- 不要提交 `.env`。
- 不要把真实 API Key 写进 README、issue、截图或聊天记录。
- Release 包不包含你的本地 API Key。
- 如果使用 GitHub Releases 作为临时视频 URL，请确认视频内容适合公开访问。

## 参考

- 阿里云百炼视觉理解文档：https://help.aliyun.com/zh/model-studio/vision
- 阿里云百炼 Qwen-Omni 文档：https://help.aliyun.com/zh/model-studio/qwen-omni
- Tauri sidecar 文档：https://v2.tauri.app/develop/sidecar/
- Tauri GitHub Actions 文档：https://v2.tauri.app/distribute/pipelines/github/
