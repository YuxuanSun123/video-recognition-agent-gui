import { createHash, randomUUID } from "node:crypto";
import { createReadStream, createWriteStream, existsSync, mkdirSync, readFileSync, statSync } from "node:fs";
import { writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join, resolve } from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const publicDir = resolve(__dirname, "public");
const cacheDir = resolve(__dirname, ".cache", "frames");
const uploadDir = resolve(__dirname, ".cache", "uploads");
const envPath = resolve(__dirname, ".env");

loadEnv(envPath);

const port = Number(process.env.PORT || 5177);
mkdirSync(cacheDir, { recursive: true });
mkdirSync(uploadDir, { recursive: true });

const configKeys = [
  "DASHSCOPE_API_KEY",
  "DASHSCOPE_BASE_URL",
  "DASHSCOPE_WORKSPACE_ID",
  "DASHSCOPE_REGION",
  "ALIYUN_VISION_MODEL",
  "ALIYUN_OMNI_MODEL",
  "OSS_ACCESS_KEY_ID",
  "OSS_ACCESS_KEY_SECRET",
  "OSS_REGION",
  "OSS_BUCKET",
  "OSS_ENDPOINT",
  "OSS_PREFIX",
  "OSS_SIGNED_URL_EXPIRES",
  "GITHUB_TOKEN",
  "GITHUB_OWNER",
  "GITHUB_REPO",
  "GITHUB_RELEASE_TAG",
  "GITHUB_RELEASE_NAME",
  "GITHUB_ASSET_PREFIX"
];

const mimeTypes = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".svg": "image/svg+xml"
};

const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, `http://${req.headers.host}`);

    if (req.method === "GET" && url.pathname === "/api/health") {
      const config = getRuntimeConfig();
      return sendJSON(res, {
        ok: true,
        configured: Boolean(config.apiKey),
        model: config.visionModel,
        visionModel: config.visionModel,
        omniModel: config.omniModel,
        baseURL: config.baseURL,
        apiKeyMasked: maskSecret(config.apiKey),
        ffmpeg: await hasFfmpeg(),
        python: await getPythonStatus()
      });
    }

    if (req.method === "GET" && url.pathname === "/api/config") {
      return sendJSON(res, getPublicConfig());
    }

    if (req.method === "POST" && url.pathname === "/api/config") {
      const body = await readJSON(req);
      const saved = await saveConfig(body);
      return sendJSON(res, saved);
    }

    if (req.method === "POST" && url.pathname === "/api/upload") {
      const uploaded = await saveUpload(req);
      return sendJSON(res, uploaded);
    }

    if (req.method === "POST" && url.pathname === "/api/oss/upload") {
      const uploaded = await uploadToOSS(req);
      return sendJSON(res, uploaded);
    }

    if (req.method === "POST" && url.pathname === "/api/github/upload") {
      const uploaded = await uploadToGitHubRelease(req);
      return sendJSON(res, uploaded);
    }

    if (req.method === "POST" && url.pathname === "/api/analyze") {
      const body = await readJSON(req);
      const result = await analyzeVideo(body);
      return sendJSON(res, result);
    }

    if (req.method === "GET" && url.pathname === "/api/frame") {
      return await serveFrame(url, res);
    }

    return serveStatic(url, res);
  } catch (error) {
    console.error(error);
    return sendJSON(res, { error: error.message || "Unexpected server error" }, 500);
  }
});

server.listen(port, () => {
  console.log(`Video shot report platform: http://localhost:${port}`);
  if (!getRuntimeConfig().apiKey) {
    console.log("DASHSCOPE_API_KEY is not configured. The platform will use demo mode.");
  }
});

function loadEnv(filePath) {
  if (!existsSync(filePath)) return;

  const values = readEnvFile(filePath);
  for (const [key, value] of Object.entries(values)) {
    if (!(key in process.env)) process.env[key] = value;
  }
}

function readEnvFile(filePath) {
  if (!existsSync(filePath)) return {};

  const values = {};
  const lines = readFileSync(filePath, "utf8").split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const equalsIndex = trimmed.indexOf("=");
    if (equalsIndex === -1) continue;

    const key = trimmed.slice(0, equalsIndex).trim();
    let value = trimmed.slice(equalsIndex + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    values[key] = value;
  }
  return values;
}

function getRuntimeConfig() {
  const fileValues = readEnvFile(envPath);
  const value = (key, fallback = "") => fileValues[key] ?? process.env[key] ?? fallback;
  const config = {
    apiKey: value("DASHSCOPE_API_KEY"),
    baseURLRaw: value("DASHSCOPE_BASE_URL"),
    workspaceId: value("DASHSCOPE_WORKSPACE_ID"),
    region: value("DASHSCOPE_REGION", "cn-beijing"),
    visionModel: value("ALIYUN_VISION_MODEL", "qwen3.6-plus"),
    omniModel: value("ALIYUN_OMNI_MODEL", "qwen3.6-plus"),
    ossAccessKeyId: value("OSS_ACCESS_KEY_ID"),
    ossAccessKeySecret: value("OSS_ACCESS_KEY_SECRET"),
    ossRegion: value("OSS_REGION", "oss-cn-beijing"),
    ossBucket: value("OSS_BUCKET"),
    ossEndpoint: value("OSS_ENDPOINT"),
    ossPrefix: value("OSS_PREFIX", "video-agent"),
    ossSignedUrlExpires: Number(value("OSS_SIGNED_URL_EXPIRES", "86400")) || 86400,
    githubToken: value("GITHUB_TOKEN"),
    githubOwner: value("GITHUB_OWNER"),
    githubRepo: value("GITHUB_REPO"),
    githubReleaseTag: value("GITHUB_RELEASE_TAG", "video-agent-temp"),
    githubReleaseName: value("GITHUB_RELEASE_NAME", "Video Agent Temporary Uploads"),
    githubAssetPrefix: value("GITHUB_ASSET_PREFIX", "video-agent")
  };
  config.baseURL = getBaseURL(config);
  return config;
}

function getBaseURL(config = getRuntimeConfig()) {
  if (config.baseURLRaw) {
    return config.baseURLRaw.replace(/\/$/, "");
  }

  if (config.workspaceId) {
    return `https://${config.workspaceId}.${config.region}.maas.aliyuncs.com/compatible-mode/v1`;
  }

  return "https://dashscope.aliyuncs.com/compatible-mode/v1";
}

function getPublicConfig() {
  const config = getRuntimeConfig();
  return {
    configured: Boolean(config.apiKey),
    apiKeyMasked: maskSecret(config.apiKey),
    baseURL: config.baseURL,
    baseURLRaw: config.baseURLRaw,
    workspaceId: config.workspaceId,
    region: config.region,
    visionModel: config.visionModel,
    omniModel: config.omniModel,
    ossConfigured: Boolean(config.ossAccessKeyId && config.ossAccessKeySecret && config.ossBucket),
    ossAccessKeyIdMasked: maskSecret(config.ossAccessKeyId),
    ossRegion: config.ossRegion,
    ossBucket: config.ossBucket,
    ossEndpoint: config.ossEndpoint,
    ossPrefix: config.ossPrefix,
    ossSignedUrlExpires: config.ossSignedUrlExpires,
    githubConfigured: Boolean(config.githubToken && config.githubOwner && config.githubRepo),
    githubTokenMasked: maskSecret(config.githubToken),
    githubOwner: config.githubOwner,
    githubRepo: config.githubRepo,
    githubReleaseTag: config.githubReleaseTag,
    githubReleaseName: config.githubReleaseName,
    githubAssetPrefix: config.githubAssetPrefix
  };
}

async function saveConfig(input) {
  const updates = {
    DASHSCOPE_BASE_URL: cleanConfigValue(input.baseURL),
    DASHSCOPE_WORKSPACE_ID: cleanConfigValue(input.workspaceId),
    DASHSCOPE_REGION: cleanConfigValue(input.region) || "cn-beijing",
    ALIYUN_VISION_MODEL: cleanConfigValue(input.visionModel) || "qwen3.6-plus",
    ALIYUN_OMNI_MODEL: cleanConfigValue(input.omniModel) || "qwen3.6-plus",
    OSS_REGION: cleanConfigValue(input.ossRegion) || "oss-cn-beijing",
    OSS_BUCKET: cleanConfigValue(input.ossBucket),
    OSS_ENDPOINT: cleanConfigValue(input.ossEndpoint),
    OSS_PREFIX: cleanConfigValue(input.ossPrefix) || "video-agent",
    OSS_SIGNED_URL_EXPIRES: String(clamp(Number(input.ossSignedUrlExpires || 86400), 600, 604800)),
    GITHUB_OWNER: cleanConfigValue(input.githubOwner),
    GITHUB_REPO: cleanConfigValue(input.githubRepo),
    GITHUB_RELEASE_TAG: cleanConfigValue(input.githubReleaseTag) || "video-agent-temp",
    GITHUB_RELEASE_NAME: cleanConfigValue(input.githubReleaseName) || "Video Agent Temporary Uploads",
    GITHUB_ASSET_PREFIX: cleanConfigValue(input.githubAssetPrefix) || "video-agent"
  };

  const apiKey = cleanConfigValue(input.apiKey);
  if (apiKey) updates.DASHSCOPE_API_KEY = apiKey;
  if (input.clearApiKey) updates.DASHSCOPE_API_KEY = "";

  const ossAccessKeyId = cleanConfigValue(input.ossAccessKeyId);
  const ossAccessKeySecret = cleanConfigValue(input.ossAccessKeySecret);
  if (ossAccessKeyId) updates.OSS_ACCESS_KEY_ID = ossAccessKeyId;
  if (ossAccessKeySecret) updates.OSS_ACCESS_KEY_SECRET = ossAccessKeySecret;
  if (input.clearOssKeys) {
    updates.OSS_ACCESS_KEY_ID = "";
    updates.OSS_ACCESS_KEY_SECRET = "";
  }

  const githubToken = cleanConfigValue(input.githubToken);
  if (githubToken) updates.GITHUB_TOKEN = githubToken;
  if (input.clearGithubToken) updates.GITHUB_TOKEN = "";

  await writeEnvUpdates(updates);

  for (const [key, value] of Object.entries(updates)) {
    process.env[key] = value;
  }

  return getPublicConfig();
}

async function writeEnvUpdates(updates) {
  const existing = existsSync(envPath) ? readFileSync(envPath, "utf8").split(/\r?\n/) : [];
  const seen = new Set();
  const lines = existing.map(line => {
    const match = line.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*=/);
    if (!match || !(match[1] in updates)) return line;
    const key = match[1];
    seen.add(key);
    return `${key}=${formatEnvValue(updates[key])}`;
  });

  if (!lines.length) {
    lines.push("# Saved from the local video shot report platform.");
  }

  for (const key of configKeys) {
    if (key in updates && !seen.has(key)) {
      lines.push(`${key}=${formatEnvValue(updates[key])}`);
    }
  }

  await writeFile(envPath, `${lines.join("\n").replace(/\n+$/, "")}\n`, "utf8");
}

function cleanConfigValue(value) {
  return String(value ?? "").trim();
}

function formatEnvValue(value) {
  const raw = String(value ?? "");
  if (!raw) return "";
  if (/^[A-Za-z0-9_./:+=@-]+$/.test(raw)) return raw;
  return JSON.stringify(raw);
}

function maskSecret(value) {
  if (!value) return "";
  if (value.length <= 10) return `${value.slice(0, 2)}****${value.slice(-2)}`;
  return `${value.slice(0, 6)}****${value.slice(-4)}`;
}

async function readJSON(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const raw = Buffer.concat(chunks).toString("utf8");
  if (!raw) return {};
  try {
    return JSON.parse(raw);
  } catch {
    throw new Error("Request body must be valid JSON.");
  }
}

async function saveUpload(req) {
  const contentType = String(req.headers["content-type"] || "application/octet-stream");
  if (!contentType.startsWith("video/")) {
    throw new Error("本地路径模式只接受 video/* 文件。");
  }

  const length = Number(req.headers["content-length"] || 0);
  const limit = 100 * 1024 * 1024;
  if (!Number.isFinite(length) || length <= 0) {
    throw new Error("无法读取上传文件大小。");
  }
  if (length > limit) {
    throw new Error("本地路径模式限制视频本身不超过 100MB。");
  }

  const originalName = decodeURIComponent(String(req.headers["x-file-name"] || "video.mp4"));
  const extension = safeExtension(originalName, contentType);
  const uploadId = `${Date.now()}-${randomUUID()}${extension}`;
  const localPath = resolve(uploadDir, uploadId);

  if (!localPath.startsWith(uploadDir)) {
    throw new Error("Invalid upload path.");
  }

  await writeRequestToFile(req, localPath, limit);

  return {
    uploadId,
    name: originalName,
    size: statSync(localPath).size,
    contentType,
    mode: "local-path",
    limitMB: 100
  };
}

function writeRequestToFile(req, targetPath, limit) {
  return new Promise((resolvePromise, reject) => {
    let bytes = 0;
    const out = createWriteStream(targetPath);

    req.on("data", chunk => {
      bytes += chunk.length;
      if (bytes > limit) {
        out.destroy();
        req.destroy(new Error("上传超过 100MB 限制。"));
      }
    });
    req.on("error", reject);
    out.on("error", reject);
    out.on("finish", resolvePromise);
    req.pipe(out);
  });
}

function safeExtension(name, contentType) {
  const fromName = extname(name).toLowerCase().replace(/[^.a-z0-9]/g, "");
  if (fromName) return fromName.slice(0, 12);
  const subtype = contentType.split("/")[1]?.split(";")[0]?.toLowerCase().replace(/[^a-z0-9]/g, "");
  return subtype ? `.${subtype.slice(0, 10)}` : ".mp4";
}

function resolveUpload(uploadId) {
  const safeId = String(uploadId || "").trim();
  if (!safeId || safeId.includes("..") || /[\\/]/.test(safeId)) {
    throw new Error("无效的本地上传文件 ID。");
  }

  const localPath = resolve(uploadDir, safeId);
  if (!localPath.startsWith(uploadDir) || !existsSync(localPath)) {
    throw new Error("找不到已上传的本地视频，请重新上传。");
  }

  const size = statSync(localPath).size;
  if (size > 100 * 1024 * 1024) {
    throw new Error("本地路径模式限制视频本身不超过 100MB。");
  }

  return { localPath, size };
}

async function uploadToOSS(req) {
  const config = getRuntimeConfig();
  if (!config.ossAccessKeyId || !config.ossAccessKeySecret || !config.ossBucket) {
    throw new Error("请先在设置页配置 OSS AccessKey、Secret 和 Bucket。");
  }

  const contentType = String(req.headers["content-type"] || "application/octet-stream");
  if (!contentType.startsWith("video/")) {
    throw new Error("OSS 公网 URL 上传只接受 video/* 文件。");
  }

  const length = Number(req.headers["content-length"] || 0);
  const limit = 2 * 1024 * 1024 * 1024;
  if (!Number.isFinite(length) || length <= 0) {
    throw new Error("无法读取上传文件大小。");
  }
  if (length > limit) {
    throw new Error("当前 OSS 上传限制为 2GB，超过后请先压缩或分片上传。");
  }

  const originalName = decodeURIComponent(String(req.headers["x-file-name"] || "video.mp4"));
  const objectKey = buildOSSObjectKey(config.ossPrefix, originalName, contentType);
  const client = await createOSSClient(config);

  const result = await client.putStream(objectKey, req, {
    contentLength: length,
    mime: contentType,
    headers: {
      "Content-Disposition": `inline; filename="${encodeURIComponent(originalName)}"`
    }
  });

  const expires = clamp(Number(config.ossSignedUrlExpires || 86400), 600, 604800);
  const signedUrl = client.signatureUrl(objectKey, {
    expires,
    method: "GET",
    response: {
      "content-type": contentType
    }
  });

  return {
    mode: "oss-url",
    name: originalName,
    size: length,
    contentType,
    bucket: config.ossBucket,
    objectKey,
    expires,
    videoUrl: signedUrl,
    ossUrl: result.url || ""
  };
}

async function createOSSClient(config) {
  const module = await import("ali-oss");
  const OSS = module.default || module;
  return new OSS({
    region: config.ossRegion,
    bucket: config.ossBucket,
    endpoint: config.ossEndpoint || undefined,
    accessKeyId: config.ossAccessKeyId,
    accessKeySecret: config.ossAccessKeySecret,
    secure: true,
    authorizationV4: true
  });
}

function buildOSSObjectKey(prefix, originalName, contentType) {
  const now = new Date();
  const yyyy = String(now.getFullYear());
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  const safePrefix = String(prefix || "video-agent")
    .replace(/\\/g, "/")
    .split("/")
    .filter(Boolean)
    .map(part => part.replace(/[^A-Za-z0-9._-]/g, "-"))
    .join("/");
  const extension = safeExtension(originalName, contentType);
  return `${safePrefix}/${yyyy}/${mm}/${dd}/${Date.now()}-${randomUUID()}${extension}`;
}

async function uploadToGitHubRelease(req) {
  const config = getRuntimeConfig();
  if (!config.githubToken || !config.githubOwner || !config.githubRepo) {
    throw new Error("请先在设置页配置 GitHub Token、Owner 和 Repo。");
  }

  const contentType = String(req.headers["content-type"] || "application/octet-stream");
  if (!contentType.startsWith("video/")) {
    throw new Error("GitHub Releases 上传只接受 video/* 文件。");
  }

  const length = Number(req.headers["content-length"] || 0);
  const limit = 2 * 1024 * 1024 * 1024;
  if (!Number.isFinite(length) || length <= 0) {
    throw new Error("无法读取上传文件大小。");
  }
  if (length > limit) {
    throw new Error("GitHub Release asset 单文件建议不超过 2GB。");
  }

  const originalName = decodeURIComponent(String(req.headers["x-file-name"] || "video.mp4"));
  const release = await getOrCreateGitHubRelease(config);
  const assetName = buildGitHubAssetName(config.githubAssetPrefix, originalName, contentType);
  const uploadBase = String(release.upload_url || "").split("{")[0];
  if (!uploadBase) {
    throw new Error("GitHub Release 没有返回 upload_url。");
  }

  const uploadUrl = `${uploadBase}?name=${encodeURIComponent(assetName)}`;
  const asset = await githubRequest(uploadUrl, {
    method: "POST",
    token: config.githubToken,
    headers: {
      "Content-Type": contentType,
      "Content-Length": String(length)
    },
    body: req,
    duplex: "half"
  });

  return {
    mode: "github-release",
    name: originalName,
    size: length,
    contentType,
    owner: config.githubOwner,
    repo: config.githubRepo,
    tag: config.githubReleaseTag,
    assetName,
    videoUrl: asset.browser_download_url,
    assetUrl: asset.url
  };
}

async function getOrCreateGitHubRelease(config) {
  const owner = encodeURIComponent(config.githubOwner);
  const repo = encodeURIComponent(config.githubRepo);
  const tag = encodeURIComponent(config.githubReleaseTag);
  const releaseUrl = `https://api.github.com/repos/${owner}/${repo}/releases/tags/${tag}`;

  try {
    return await githubRequest(releaseUrl, {
      method: "GET",
      token: config.githubToken
    });
  } catch (error) {
    if (!/GitHub API 404/.test(error.message)) throw error;
  }

  return githubRequest(`https://api.github.com/repos/${owner}/${repo}/releases`, {
    method: "POST",
    token: config.githubToken,
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      tag_name: config.githubReleaseTag,
      name: config.githubReleaseName,
      body: "Temporary video uploads for the local video agent platform.",
      draft: false,
      prerelease: false
    })
  });
}

async function githubRequest(url, options) {
  const response = await fetch(url, {
    method: options.method || "GET",
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${options.token}`,
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "video-shot-report-platform",
      ...(options.headers || {})
    },
    body: options.body,
    duplex: options.duplex
  });

  const text = await response.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { message: text };
  }

  if (!response.ok) {
    throw new Error(`GitHub API ${response.status}: ${data.message || response.statusText}`);
  }

  return data;
}

function buildGitHubAssetName(prefix, originalName, contentType) {
  const safePrefix = String(prefix || "video-agent").replace(/[^A-Za-z0-9._-]/g, "-");
  const extension = safeExtension(originalName, contentType);
  return `${safePrefix}-${Date.now()}-${randomUUID()}${extension}`;
}

async function analyzeVideo(input) {
  const config = getRuntimeConfig();
  const videoUrl = String(input.videoUrl || "").trim();
  const videoDataUrl = String(input.videoDataUrl || "").trim();
  const uploadId = String(input.uploadId || "").trim();
  const title = String(input.title || "").trim() || "未命名视频";
  const fpsPreference = normalizeFpsPreference(input.fps);
  const analysisMode = input.analysisMode === "omni" ? "omni" : "vision";
  const selectedModel = analysisMode === "omni" ? config.omniModel : config.visionModel;
  const canUnderstandAudio = analysisMode === "omni";

  if (!config.apiKey || input.demoMode) {
    await wait(650);
    return {
      mode: "demo",
      report: demoReport({ title, videoUrl }),
      raw: null,
      note: "未配置 DASHSCOPE_API_KEY，当前返回演示报告。"
    };
  }

  if (uploadId) {
    if (analysisMode === "omni") {
      throw new Error("100MB 本地路径模式当前走 DashScope 视觉 SDK。请切换到“视觉：大文件拉片”；如需声音理解，请使用 OSS/公网 URL + 全模态模式。");
    }

    const { localPath } = resolveUpload(uploadId);
    const fpsDecision = await decideFps({
      preference: fpsPreference,
      localPath,
      durationHint: input.videoDuration
    });
    const prompt = buildAnalysisPrompt({
      title,
      episode: input.episode,
      fps: fpsDecision.label,
      canUnderstandAudio: false,
      subtitleText: input.subtitleText,
      customPrompt: input.prompt
    });
    return callLocalVideoSDK({
      config,
      localPath,
      title,
      videoUrl: "",
      fps: fpsDecision.value,
      prompt,
      model: config.visionModel
    });
  }

  if (!videoUrl && !videoDataUrl) {
    throw new Error("请填写视频公网 URL，或上传小于 Base64 限制的本地视频文件。");
  }

  if (videoUrl && !/^https?:\/\//i.test(videoUrl)) {
    throw new Error("视频 URL 需要是公网可访问的 HTTP/HTTPS 地址。");
  }

  if (videoDataUrl && !/^data:video\//i.test(videoDataUrl)) {
    throw new Error("本地上传只接受 video/* 文件。");
  }

  if (videoDataUrl && videoDataUrl.length > 10 * 1024 * 1024) {
    throw new Error("Base64 编码后的视频超过 10MB。请改用公网 URL 或 OSS 临时 URL。");
  }

  const fpsDecision = await decideFps({
    preference: fpsPreference,
    videoUrl: videoUrl || "",
    durationHint: input.videoDuration
  });
  const prompt = buildAnalysisPrompt({
    title,
    episode: input.episode,
    fps: fpsDecision.label,
    canUnderstandAudio,
    subtitleText: input.subtitleText,
    customPrompt: input.prompt
  });

  const messages = [
    {
      role: "user",
      content: [
        {
          type: "video_url",
          video_url: { url: videoUrl || videoDataUrl },
          fps: fpsDecision.value
        },
        {
          type: "text",
          text: prompt
        }
      ]
    }
  ];

  const payload = {
    model: selectedModel,
    messages,
    temperature: 0.2,
    enable_thinking: false
  };

  if (analysisMode === "omni") {
    delete payload.enable_thinking;
    payload.messages = messages;
    payload.stream = true;
    payload.stream_options = { include_usage: true };
    payload.modalities = ["text"];
    return callOmniStream(payload, { title, videoUrl, fps: fpsDecision.value, contentFallback: "" }, config);
  }

  const response = await fetch(`${config.baseURL}/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${config.apiKey}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  const text = await response.text();
  let raw;
  try {
    raw = JSON.parse(text);
  } catch {
    raw = { text };
  }

  if (!response.ok) {
    throw new Error(raw?.error?.message || raw?.message || `Aliyun API request failed: ${response.status}`);
  }

  const content = raw?.choices?.[0]?.message?.content ?? raw?.output?.choices?.[0]?.message?.content?.[0]?.text ?? "";
  const parsed = parseModelJSON(content);
  const report = normalizeReport(parsed, { title, videoUrl, fps: fpsDecision.value, content });

  return {
    mode: "api",
    report,
    usage: raw?.usage,
    raw
  };
}

async function callLocalVideoSDK({ config, localPath, title, videoUrl, fps, prompt, model }) {
  const scriptPath = resolve(__dirname, "scripts", "dashscope_local_video.py");
  if (!existsSync(scriptPath)) {
    throw new Error("缺少 DashScope SDK 辅助脚本。");
  }

  const python = getPythonCommand();
  const input = {
    apiKey: config.apiKey,
    model,
    fileUri: pathToFileURL(localPath).href,
    fps,
    prompt,
    baseHttpApiUrl: getDashScopeSdkBaseURL(config)
  };

  const result = await runPythonJSON(python.command, [...python.args, scriptPath], input);
  const content = result.content || result.rawText || "";
  const parsed = parseModelJSON(content);
  const report = normalizeReport(parsed, { title, videoUrl, fps, content });

  return {
    mode: "api-local-path",
    report,
    usage: result.usage,
    raw: result.raw
  };
}

function runPythonJSON(command, args, input) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(command, args, {
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
      env: {
        ...process.env,
        PYTHONIOENCODING: "utf-8"
      }
    });

    let stdout = "";
    let stderr = "";
    child.stdout.on("data", chunk => { stdout += chunk.toString(); });
    child.stderr.on("data", chunk => { stderr += chunk.toString(); });
    child.on("error", error => reject(new Error(`无法启动 Python：${error.message}`)));
    child.on("close", code => {
      if (code !== 0) {
        const message = stderr || stdout || `Python exited with code ${code}`;
        reject(new Error(message.trim()));
        return;
      }

      try {
        resolvePromise(JSON.parse(stdout));
      } catch {
        reject(new Error(`Python 返回了非 JSON 内容：${stdout || stderr}`));
      }
    });

    child.stdin.end(JSON.stringify(input), "utf8");
  });
}

function getPythonCommand() {
  if (process.env.PYTHON_EXECUTABLE) {
    return { command: process.env.PYTHON_EXECUTABLE, args: [] };
  }
  if (process.platform === "win32") {
    return { command: "py", args: ["-3"] };
  }
  return { command: "python3", args: [] };
}

function getDashScopeSdkBaseURL(config) {
  if (!config.baseURLRaw) return "";
  return config.baseURLRaw
    .replace(/\/compatible-mode\/v1\/?$/, "/api/v1")
    .replace(/\/$/, "");
}

async function callOmniStream(payload, fallback, config) {
  const response = await fetch(`${config.baseURL}/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${config.apiKey}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  const text = await response.text();
  if (!response.ok) {
    const raw = parseJSONSafe(text);
    throw new Error(raw?.error?.message || raw?.message || `Aliyun Omni request failed: ${response.status}`);
  }

  const parsed = parseSSE(text);
  const modelJSON = parseModelJSON(parsed.content);
  const report = normalizeReport(modelJSON, { ...fallback, content: parsed.content });

  return {
    mode: "api-omni",
    report,
    usage: parsed.usage,
    raw: { chunks: parsed.chunks }
  };
}

function normalizeFpsPreference(value) {
  if (String(value || "").trim().toLowerCase() === "auto") {
    return { mode: "auto", value: null };
  }
  return { mode: "manual", value: clamp(Number(value || 1), 0.1, 10) };
}

async function decideFps({ preference, localPath = "", videoUrl = "", durationHint = 0 }) {
  if (preference.mode === "manual") {
    return {
      value: preference.value,
      label: `${preference.value} fps（手动）`,
      duration: 0,
      reason: "manual"
    };
  }

  const hinted = Number(durationHint);
  const duration = Number.isFinite(hinted) && hinted > 0
    ? hinted
    : await probeVideoDuration(localPath || videoUrl);
  const value = chooseFpsByDuration(duration);
  const label = duration
    ? `${value} fps（自动，片长约 ${formatDuration(duration)}）`
    : `${value} fps（自动，未能读取片长）`;

  return { value, label, duration: duration || 0, reason: "auto" };
}

function chooseFpsByDuration(duration) {
  if (!Number.isFinite(duration) || duration <= 0) return 1;
  if (duration <= 60) return 2;
  if (duration <= 10 * 60) return 1;
  if (duration <= 45 * 60) return 0.5;
  return 0.2;
}

function probeVideoDuration(source) {
  if (!source) return Promise.resolve(0);

  return new Promise(resolvePromise => {
    const child = spawn("ffprobe", [
      "-v", "error",
      "-show_entries", "format=duration",
      "-of", "default=noprint_wrappers=1:nokey=1",
      source
    ], { windowsHide: true });

    let stdout = "";
    child.stdout.on("data", chunk => { stdout += chunk.toString(); });
    child.on("error", () => resolvePromise(0));
    const timer = setTimeout(() => {
      child.kill();
      resolvePromise(0);
    }, 8000);
    child.on("close", () => {
      clearTimeout(timer);
      const duration = Number.parseFloat(stdout.trim());
      resolvePromise(Number.isFinite(duration) ? duration : 0);
    });
  });
}

function formatDuration(seconds) {
  const safe = Math.max(0, Math.round(seconds));
  const h = Math.floor(safe / 3600);
  const m = Math.floor((safe % 3600) / 60);
  const s = safe % 60;
  if (h) return `${h}小时${m}分`;
  if (m) return `${m}分${s}秒`;
  return `${s}秒`;
}

function buildAnalysisPrompt({ title, episode, fps, canUnderstandAudio, subtitleText, customPrompt }) {
  const audioInstruction = canUnderstandAudio
    ? "请同时分析视频中的对白、音乐、环境声、声画关系；声音/音乐列需要直接基于音频理解填写。"
    : "当前视觉模式不保证理解视频音频；声音/音乐列优先使用可见字幕、画面文字和用户提供的字幕/转写，无法判断时写“需结合音轨或字幕”。";

  return [
    "你是一名电影学院拉片分析师。请基于视频画面生成逐镜拉片报告，语言使用中文。",
    "只输出 JSON，不要 Markdown，不要代码块，不要解释。",
    "JSON 结构必须为：",
    '{"meta":{"title":"片名","episode":"集数或片段","duration":"片长","sceneCount":0,"shotCount":0,"basis":"分析依据"},"scenes":[{"id":1,"title":"场景标题","start":"00:00","end":"00:00","summary":"场景概述"}],"shots":[{"shot":"镜 1","scene":"场景一","timecode":"00:00-00:10","start":0,"end":10,"shotSize":"全景/中景/近景/特写/极近景","camera":"固定/推/拉/摇/移/跟/手持","visual":"画面内容与人物动作","audio":"声音/音乐/字幕；如果不能判断请说明需结合音轨或字幕","analysis":"电影语言分析注释"}]}',
    `片名：${title}`,
    `集数/片段：${episode || "未提供"}`,
    `抽帧 fps：${fps}`,
    "拆分规则：优先按明显镜头转换、构图变化、场景变化、人物动作阶段拆分；如果无法确认真实剪辑点，可按 8-12 秒粒度估算。",
    "分析重点：场景、人物、动作、空间关系、景别、镜头运动、构图、色彩、叙事功能、转折点。",
    audioInstruction,
    subtitleText ? `额外音轨/字幕文本：${subtitleText}` : "额外音轨/字幕文本：未提供。",
    customPrompt ? `用户补充要求：${customPrompt}` : ""
  ].filter(Boolean).join("\n");
}

function parseModelJSON(content) {
  if (typeof content !== "string") return content || {};
  const cleaned = content.trim().replace(/^```json\s*/i, "").replace(/^```\s*/i, "").replace(/```$/i, "").trim();
  try {
    return JSON.parse(cleaned);
  } catch {
    const match = cleaned.match(/\{[\s\S]*\}/);
    if (match) {
      try {
        return JSON.parse(match[0]);
      } catch {
        return { rawText: content };
      }
    }
    return { rawText: content };
  }
}

function parseJSONSafe(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function parseSSE(text) {
  const chunks = [];
  let content = "";
  let usage = null;

  for (const block of text.split(/\n\n+/)) {
    const dataLines = block
      .split(/\r?\n/)
      .filter(line => line.startsWith("data:"))
      .map(line => line.slice(5).trim());

    for (const dataLine of dataLines) {
      if (!dataLine || dataLine === "[DONE]") continue;
      const chunk = parseJSONSafe(dataLine);
      if (!chunk) continue;

      chunks.push(chunk);
      const delta = chunk?.choices?.[0]?.delta;
      const message = chunk?.choices?.[0]?.message;
      const piece = delta?.content ?? message?.content ?? "";
      if (typeof piece === "string") content += piece;
      if (chunk.usage) usage = chunk.usage;
    }
  }

  return { content, usage, chunks };
}

function normalizeReport(input, fallback = {}) {
  const meta = input?.meta || {};
  const shots = Array.isArray(input?.shots) ? input.shots : [];
  const normalizedShots = shots.map((shot, index) => {
    const timecode = String(shot.timecode || shot.time || shot.timestamp || "");
    const start = Number.isFinite(Number(shot.start)) ? Number(shot.start) : parseStartSeconds(timecode, index * 10);
    return {
      shot: shot.shot || shot.id || `镜 ${index + 1}`,
      scene: shot.scene || "",
      timecode: timecode || formatRange(start, Number(shot.end || start + 10)),
      start,
      end: Number.isFinite(Number(shot.end)) ? Number(shot.end) : start + 10,
      shotSize: shot.shotSize || shot.size || shot["景别"] || "未标注",
      camera: shot.camera || shot.motion || shot["镜头运动"] || "未标注",
      visual: shot.visual || shot.content || shot["画面内容"] || "",
      audio: shot.audio || shot.sound || shot["声音"] || "",
      analysis: shot.analysis || shot.note || shot["分析注释"] || ""
    };
  });

  return {
    meta: {
      title: meta.title || fallback.title || "未命名视频",
      episode: meta.episode || "",
      duration: meta.duration || "",
      sceneCount: Number(meta.sceneCount || input?.scenes?.length || 0),
      shotCount: Number(meta.shotCount || normalizedShots.length || 0),
      basis: meta.basis || `基于 ${fallback.fps || 1} fps 抽帧的视觉理解分析`
    },
    scenes: Array.isArray(input?.scenes) ? input.scenes : [],
    shots: normalizedShots.length ? normalizedShots : [{
      shot: "原始输出",
      scene: "",
      timecode: "",
      start: 0,
      end: 0,
      shotSize: "",
      camera: "",
      visual: fallback.content || input?.rawText || "模型返回内容未能解析为逐镜 JSON。",
      audio: "",
      analysis: "请调整提示词后重试，或在结果详情中查看 raw 输出。"
    }],
    videoUrl: fallback.videoUrl || ""
  };
}

function demoReport({ title, videoUrl }) {
  return {
    meta: {
      title,
      episode: "样例片段",
      duration: "约 01:10",
      sceneCount: 3,
      shotCount: 8,
      basis: "演示数据：模拟音视频逐镜电影学院分析"
    },
    scenes: [
      { id: 1, title: "夜班开场", start: "00:00", end: "00:30", summary: "以冷静的工作环境建立人物处境。" },
      { id: 2, title: "空间转换", start: "00:30", end: "00:50", summary: "视角从局部细节扩展到人物与空间关系。" },
      { id: 3, title: "外部凝视", start: "00:50", end: "01:10", summary: "通过橱窗与远景强调角色的孤独感。" }
    ],
    shots: [
      {
        shot: "镜 1",
        scene: "夜班开场",
        timecode: "00:00-00:10",
        start: 0,
        end: 10,
        shotSize: "极近景",
        camera: "固定 / 俯视",
        visual: "黑白画面中，食物纹理占据画面，形成抽象的漩涡感。",
        audio: "低频环境声进入，音乐弱化人物对白。",
        analysis: "以物而非人开场，先建立单调工作环境的触感和节奏。"
      },
      {
        shot: "镜 2",
        scene: "夜班开场",
        timecode: "00:10-00:20",
        start: 10,
        end: 20,
        shotSize: "近景",
        camera: "固定",
        visual: "柜台与餐具形成遮挡，人物面部被部分隐藏。",
        audio: "餐具碰撞与背景音乐延续，对白较少。",
        analysis: "遮挡将人物变成工作流程的一部分，弱化身份。"
      },
      {
        shot: "镜 3",
        scene: "夜班开场",
        timecode: "00:20-00:30",
        start: 20,
        end: 30,
        shotSize: "中近景",
        camera: "固定",
        visual: "人物在后厨操作，玻璃与设备把画面切成多个层次。",
        audio: "环境声 / 待转写确认。",
        analysis: "格栅式构图强化被观看和被困住的感觉。"
      },
      {
        shot: "镜 4",
        scene: "空间转换",
        timecode: "00:30-00:40",
        start: 30,
        end: 40,
        shotSize: "全景",
        camera: "固定",
        visual: "店内全景，人物被放入明亮但封闭的服务空间。",
        audio: "环境声 / 待转写确认。",
        analysis: "全景从个人状态转向社会角色，角色像展品一样被橱窗框住。"
      },
      {
        shot: "镜 5",
        scene: "空间转换",
        timecode: "00:40-00:50",
        start: 40,
        end: 50,
        shotSize: "中近景",
        camera: "固定",
        visual: "人物继续重复动作，前景有明显遮挡。",
        audio: "环境声 / 待转写确认。",
        analysis: "重复动作构成节拍，表现日常劳动的压抑。"
      },
      {
        shot: "镜 6",
        scene: "外部凝视",
        timecode: "00:50-01:00",
        start: 50,
        end: 60,
        shotSize: "全景",
        camera: "固定",
        visual: "店外夜景，橱窗成为内外世界的分隔线。",
        audio: "背景音乐 / 待转写确认。",
        analysis: "外部视角让人物处境变得客观，孤独感被空间放大。"
      },
      {
        shot: "镜 7",
        scene: "外部凝视",
        timecode: "01:00-01:10",
        start: 60,
        end: 70,
        shotSize: "全景",
        camera: "固定 / 高角",
        visual: "储物间和监控画面并置，人物在狭窄空间中移动。",
        audio: "环境声 / 待转写确认。",
        analysis: "监控画面暗示被规训的日常，强化人物的偏执与警觉。"
      },
      {
        shot: "镜 8",
        scene: "外部凝视",
        timecode: "01:10-01:20",
        start: 70,
        end: 80,
        shotSize: "中景",
        camera: "固定",
        visual: "人物在工作空间边缘停顿，画面保留大量环境信息。",
        audio: "环境声 / 待转写确认。",
        analysis: "停顿让前面的机械节奏出现裂缝，给后续情绪转折留下空间。"
      }
    ],
    videoUrl
  };
}

async function serveFrame(url, res) {
  const videoUrl = url.searchParams.get("videoUrl") || "";
  const time = url.searchParams.get("time") || "0";

  if (!/^https?:\/\//i.test(videoUrl)) {
    return sendJSON(res, { error: "Frame extraction needs an HTTP/HTTPS video URL." }, 400);
  }

  const seconds = parseStartSeconds(time, 0);
  const key = createHash("sha1").update(`${videoUrl}|${seconds}`).digest("hex");
  const outPath = join(cacheDir, `${key}.jpg`);

  if (!existsSync(outPath)) {
    try {
      await extractFrame(videoUrl, seconds, outPath);
    } catch (error) {
      console.warn(`Frame extraction failed: ${error.message}`);
      return sendFramePlaceholder(res, "截图不可用");
    }
  }

  res.writeHead(200, {
    "Content-Type": "image/jpeg",
    "Cache-Control": "public, max-age=86400"
  });
  createReadStream(outPath).pipe(res);
}

function sendFramePlaceholder(res, label) {
  const safeLabel = escapeXML(label);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="352" height="198" viewBox="0 0 352 198"><rect width="352" height="198" fill="#172330"/><rect x="1" y="1" width="350" height="196" fill="none" stroke="#303746"/><text x="176" y="102" text-anchor="middle" fill="#9aa6b8" font-family="Arial, sans-serif" font-size="18">${safeLabel}</text></svg>`;
  res.writeHead(200, {
    "Content-Type": "image/svg+xml; charset=utf-8",
    "Cache-Control": "no-store"
  });
  res.end(svg);
}

function escapeXML(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function extractFrame(videoUrl, seconds, outPath) {
  return new Promise((resolvePromise, reject) => {
    const args = [
      "-hide_banner",
      "-loglevel", "error",
      "-ss", String(Math.max(0, seconds)),
      "-i", videoUrl,
      "-frames:v", "1",
      "-q:v", "3",
      "-y",
      outPath
    ];
    const child = spawn("ffmpeg", args);
    let error = "";
    child.stderr.on("data", chunk => { error += chunk.toString(); });
    child.on("error", reject);
    child.on("close", code => {
      if (code === 0 && existsSync(outPath)) resolvePromise();
      else reject(new Error(error || `ffmpeg exited with code ${code}`));
    });
  });
}

async function hasFfmpeg() {
  return new Promise(resolvePromise => {
    const child = spawn("ffmpeg", ["-version"]);
    child.on("error", () => resolvePromise(false));
    child.on("close", code => resolvePromise(code === 0));
  });
}

async function getPythonStatus() {
  const python = getPythonCommand();
  return new Promise(resolvePromise => {
    const child = spawn(python.command, [...python.args, "-c", "import dashscope, sys; print(getattr(dashscope, '__version__', 'installed'))"], {
      windowsHide: true
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", chunk => { stdout += chunk.toString(); });
    child.stderr.on("data", chunk => { stderr += chunk.toString(); });
    child.on("error", error => resolvePromise({ ok: false, command: [python.command, ...python.args].join(" "), error: error.message }));
    child.on("close", code => {
      resolvePromise({
        ok: code === 0,
        command: [python.command, ...python.args].join(" "),
        version: code === 0 ? stdout.trim() : "",
        error: code === 0 ? "" : (stderr || stdout).trim()
      });
    });
  });
}

function serveStatic(url, res) {
  let pathname = decodeURIComponent(url.pathname);
  if (pathname === "/") pathname = "/index.html";

  const requestedPath = resolve(publicDir, `.${pathname}`);
  if (!requestedPath.startsWith(publicDir) || !existsSync(requestedPath) || statSync(requestedPath).isDirectory()) {
    res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("Not found");
    return;
  }

  const type = mimeTypes[extname(requestedPath)] || "application/octet-stream";
  res.writeHead(200, { "Content-Type": type });
  createReadStream(requestedPath).pipe(res);
}

function sendJSON(res, data, status = 200) {
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify(data, null, 2));
}

function parseStartSeconds(timecode, fallback) {
  if (Number.isFinite(Number(timecode))) return Number(timecode);
  const first = String(timecode || "").split("-")[0].trim();
  const parts = first.split(":").map(Number);
  if (parts.some(Number.isNaN)) return fallback;
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  return Number.isFinite(parts[0]) ? parts[0] : fallback;
}

function formatRange(start, end) {
  return `${formatTime(start)}-${formatTime(end)}`;
}

function formatTime(seconds) {
  const safe = Math.max(0, Math.round(seconds));
  const h = Math.floor(safe / 3600);
  const m = Math.floor((safe % 3600) / 60);
  const s = safe % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(s).padStart(2, "0");
  return h ? `${String(h).padStart(2, "0")}:${mm}:${ss}` : `${mm}:${ss}`;
}

function clamp(value, min, max) {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, value));
}

function wait(ms) {
  return new Promise(resolvePromise => setTimeout(resolvePromise, ms));
}
