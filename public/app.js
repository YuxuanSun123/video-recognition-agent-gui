const state = {
  report: null,
  health: null,
  localVideoDataUrl: "",
  localVideoObjectUrl: "",
  localVideoName: "",
  localVideoTooLarge: false,
  uploadId: ""
};

const els = {
  pageEyebrow: document.querySelector("#pageEyebrow"),
  pageTitle: document.querySelector("#pageTitle"),
  analysisToolbar: document.querySelector("#analysisToolbar"),
  apiStatus: document.querySelector("#apiStatus"),
  apiHint: document.querySelector("#apiHint"),
  videoUrl: document.querySelector("#videoUrl"),
  title: document.querySelector("#title"),
  fps: document.querySelector("#fps"),
  analysisMode: document.querySelector("#analysisMode"),
  uploadMode: document.querySelector("#uploadMode"),
  videoFile: document.querySelector("#videoFile"),
  subtitleText: document.querySelector("#subtitleText"),
  prompt: document.querySelector("#prompt"),
  runAnalysis: document.querySelector("#runAnalysis"),
  exportMarkdown: document.querySelector("#exportMarkdown"),
  exportCsv: document.querySelector("#exportCsv"),
  sourcePreview: document.querySelector("#sourcePreview"),
  emptyPreview: document.querySelector("#emptyPreview"),
  reportTitle: document.querySelector("#reportTitle"),
  reportSubtitle: document.querySelector("#reportSubtitle"),
  sceneCount: document.querySelector("#sceneCount"),
  shotCount: document.querySelector("#shotCount"),
  basis: document.querySelector("#basis"),
  sceneFilter: document.querySelector("#sceneFilter"),
  search: document.querySelector("#search"),
  shotRows: document.querySelector("#shotRows"),
  progressLine: document.querySelector("#progressLine"),
  settingsPage: document.querySelector("#settingsPage"),
  configForm: document.querySelector("#configForm"),
  configApiKey: document.querySelector("#configApiKey"),
  configWorkspace: document.querySelector("#configWorkspace"),
  configRegion: document.querySelector("#configRegion"),
  configBaseUrl: document.querySelector("#configBaseUrl"),
  configVisionModel: document.querySelector("#configVisionModel"),
  configOmniModel: document.querySelector("#configOmniModel"),
  configOssAccessKeyId: document.querySelector("#configOssAccessKeyId"),
  configOssAccessKeySecret: document.querySelector("#configOssAccessKeySecret"),
  configOssRegion: document.querySelector("#configOssRegion"),
  configOssBucket: document.querySelector("#configOssBucket"),
  configOssEndpoint: document.querySelector("#configOssEndpoint"),
  configOssPrefix: document.querySelector("#configOssPrefix"),
  configOssExpires: document.querySelector("#configOssExpires"),
  configGithubToken: document.querySelector("#configGithubToken"),
  configGithubOwner: document.querySelector("#configGithubOwner"),
  configGithubRepo: document.querySelector("#configGithubRepo"),
  configGithubReleaseTag: document.querySelector("#configGithubReleaseTag"),
  configGithubReleaseName: document.querySelector("#configGithubReleaseName"),
  configGithubAssetPrefix: document.querySelector("#configGithubAssetPrefix"),
  apiKeyMasked: document.querySelector("#apiKeyMasked"),
  ossKeyMasked: document.querySelector("#ossKeyMasked"),
  githubTokenMasked: document.querySelector("#githubTokenMasked"),
  resolvedBaseUrl: document.querySelector("#resolvedBaseUrl"),
  saveConfig: document.querySelector("#saveConfig"),
  reloadConfig: document.querySelector("#reloadConfig"),
  clearApiKey: document.querySelector("#clearApiKey"),
  clearOssKeys: document.querySelector("#clearOssKeys"),
  clearGithubToken: document.querySelector("#clearGithubToken"),
  configStatus: document.querySelector("#configStatus")
};

boot();

async function boot() {
  bindEvents();
  updateUploadModeHint();
  await loadHealth();
  await loadConfig();
  await runDemo();
}

function bindEvents() {
  els.runAnalysis.addEventListener("click", runAnalysis);
  els.videoUrl.addEventListener("input", updateVideoPreview);
  els.search.addEventListener("input", renderRows);
  els.sceneFilter.addEventListener("change", renderRows);
  els.exportMarkdown.addEventListener("click", exportMarkdown);
  els.exportCsv.addEventListener("click", exportCsv);
  document.querySelectorAll(".nav-item").forEach(button => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".nav-item").forEach(item => item.classList.remove("active"));
      button.classList.add("active");
      showPage(button.dataset.page || "analysis");
    });
  });
  els.configForm.addEventListener("submit", saveConfig);
  els.reloadConfig.addEventListener("click", loadConfig);
  els.clearApiKey.addEventListener("click", clearSavedApiKey);
  els.clearOssKeys.addEventListener("click", clearSavedOssKeys);
  els.clearGithubToken.addEventListener("click", clearSavedGithubToken);
  els.videoFile.addEventListener("change", handleVideoFile);
  els.uploadMode.addEventListener("change", updateUploadModeHint);
  window.addEventListener("focus", loadHealth);
}

function showPage(page) {
  const analysisSections = document.querySelectorAll(".input-band, .prompt-band, .report-cover, .table-tools, .report-table-wrap");
  const isSettings = page === "settings";

  analysisSections.forEach(section => section.classList.toggle("hidden", isSettings));
  els.settingsPage.classList.toggle("hidden", !isSettings);
  els.analysisToolbar.classList.toggle("hidden", isSettings);

  if (isSettings) {
    els.pageEyebrow.textContent = "Local configuration";
    els.pageTitle.textContent = "API 设置";
    setProgress("正在编辑本地 API 配置");
    loadConfig();
    return;
  }

  els.pageEyebrow.textContent = "Shot-by-shot report";
  els.pageTitle.textContent = "视频识别 Agent 承载平台";

  if (page === "analysis") {
    setProgress("已切回分析任务");
  } else if (page === "library") {
    setProgress("报告库会在任务持久化后接入");
  } else if (page === "prompts") {
    setProgress("提示词页会在模板管理接入后开放");
  }
}

function updateUploadModeHint() {
  const hint = document.querySelector(".file-field span");
  if (!hint) return;
  if (els.uploadMode.value === "oss") {
    hint.textContent = "上传到 OSS，生成签名公网 URL";
  } else if (els.uploadMode.value === "github") {
    hint.textContent = "上传到 GitHub Release，生成下载 URL";
  } else {
    hint.textContent = "上传到本机后端；100MB 本地路径模式";
  }
}

async function loadHealth() {
  try {
    const health = await fetchJSON("/api/health");
    state.health = health;
    els.apiStatus.textContent = health.configured ? "已配置" : "演示模式";
    els.apiStatus.style.color = health.configured ? "var(--green)" : "var(--gold)";
    const sdkStatus = health.python?.ok ? "SDK 已就绪" : "本地 SDK 未安装";
    els.apiHint.textContent = health.configured
      ? `视频 ${health.visionModel} / 声音 ${health.omniModel} / ${sdkStatus}`
      : "未检测到 DASHSCOPE_API_KEY，可先用演示数据查看平台。";
  } catch (error) {
    els.apiStatus.textContent = "后端异常";
    els.apiStatus.style.color = "var(--red)";
    els.apiHint.textContent = error.message;
  }
}

async function loadConfig() {
  try {
    const config = await fetchJSON("/api/config");
    els.configStatus.classList.remove("error-text");
    els.configApiKey.value = "";
    els.configWorkspace.value = config.workspaceId || "";
    els.configRegion.value = config.region || "cn-beijing";
    els.configBaseUrl.value = config.baseURLRaw || "";
    els.configVisionModel.value = config.visionModel || "qwen3.7-plus";
    els.configOmniModel.value = config.omniModel || "qwen3.5-omni-plus";
    els.configOssAccessKeyId.value = "";
    els.configOssAccessKeySecret.value = "";
    els.configOssRegion.value = config.ossRegion || "oss-cn-beijing";
    els.configOssBucket.value = config.ossBucket || "";
    els.configOssEndpoint.value = config.ossEndpoint || "";
    els.configOssPrefix.value = config.ossPrefix || "video-agent";
    els.configOssExpires.value = config.ossSignedUrlExpires || 86400;
    els.configGithubToken.value = "";
    els.configGithubOwner.value = config.githubOwner || "";
    els.configGithubRepo.value = config.githubRepo || "";
    els.configGithubReleaseTag.value = config.githubReleaseTag || "video-agent-temp";
    els.configGithubReleaseName.value = config.githubReleaseName || "Video Agent Temporary Uploads";
    els.configGithubAssetPrefix.value = config.githubAssetPrefix || "video-agent";
    els.apiKeyMasked.textContent = config.configured
      ? `已保存：${config.apiKeyMasked}`
      : "未保存密钥";
    els.ossKeyMasked.textContent = config.ossConfigured
      ? `已保存：${config.ossAccessKeyIdMasked}`
      : "未保存 OSS Key";
    els.githubTokenMasked.textContent = config.githubConfigured
      ? `已保存：${config.githubTokenMasked}`
      : "未保存 GitHub Token";
    els.resolvedBaseUrl.textContent = `实际请求地址：${config.baseURL}`;
    els.configStatus.textContent = "配置已读取";
    return config;
  } catch (error) {
    els.configStatus.textContent = error.message;
    els.configStatus.classList.add("error-text");
    return null;
  }
}

async function saveConfig(event) {
  event.preventDefault();
  els.saveConfig.disabled = true;
  els.configStatus.classList.remove("error-text");
  els.configStatus.textContent = "正在保存到 .env...";

  try {
    const payload = {
      apiKey: els.configApiKey.value.trim(),
      workspaceId: els.configWorkspace.value.trim(),
      region: els.configRegion.value.trim(),
      baseURL: els.configBaseUrl.value.trim(),
      visionModel: els.configVisionModel.value.trim(),
      omniModel: els.configOmniModel.value.trim(),
      ossAccessKeyId: els.configOssAccessKeyId.value.trim(),
      ossAccessKeySecret: els.configOssAccessKeySecret.value.trim(),
      ossRegion: els.configOssRegion.value.trim(),
      ossBucket: els.configOssBucket.value.trim(),
      ossEndpoint: els.configOssEndpoint.value.trim(),
      ossPrefix: els.configOssPrefix.value.trim(),
      ossSignedUrlExpires: Number(els.configOssExpires.value || 86400),
      githubToken: els.configGithubToken.value.trim(),
      githubOwner: els.configGithubOwner.value.trim(),
      githubRepo: els.configGithubRepo.value.trim(),
      githubReleaseTag: els.configGithubReleaseTag.value.trim(),
      githubReleaseName: els.configGithubReleaseName.value.trim(),
      githubAssetPrefix: els.configGithubAssetPrefix.value.trim()
    };

    const config = await fetchJSON("/api/config", {
      method: "POST",
      body: JSON.stringify(payload)
    });

    els.configApiKey.value = "";
    await loadHealth();
    await loadConfig();
    els.configStatus.textContent = config.configured ? "已保存，当前 API 可用" : "已保存模型配置，但还没有 API Key";
  } catch (error) {
    els.configStatus.textContent = error.message;
    els.configStatus.classList.add("error-text");
  } finally {
    els.saveConfig.disabled = false;
  }
}

async function clearSavedApiKey() {
  els.clearApiKey.disabled = true;
  els.configStatus.classList.remove("error-text");
  els.configStatus.textContent = "正在清空 API Key...";

  try {
    await fetchJSON("/api/config", {
      method: "POST",
      body: JSON.stringify({
        clearApiKey: true,
        workspaceId: els.configWorkspace.value.trim(),
        region: els.configRegion.value.trim(),
        baseURL: els.configBaseUrl.value.trim(),
        visionModel: els.configVisionModel.value.trim(),
        omniModel: els.configOmniModel.value.trim(),
        ossRegion: els.configOssRegion.value.trim(),
        ossBucket: els.configOssBucket.value.trim(),
        ossEndpoint: els.configOssEndpoint.value.trim(),
        ossPrefix: els.configOssPrefix.value.trim(),
        ossSignedUrlExpires: Number(els.configOssExpires.value || 86400),
        githubOwner: els.configGithubOwner.value.trim(),
        githubRepo: els.configGithubRepo.value.trim(),
        githubReleaseTag: els.configGithubReleaseTag.value.trim(),
        githubReleaseName: els.configGithubReleaseName.value.trim(),
        githubAssetPrefix: els.configGithubAssetPrefix.value.trim()
      })
    });
    await loadHealth();
    await loadConfig();
    els.configStatus.textContent = "API Key 已清空";
  } catch (error) {
    els.configStatus.textContent = error.message;
    els.configStatus.classList.add("error-text");
  } finally {
    els.clearApiKey.disabled = false;
  }
}

async function clearSavedOssKeys() {
  els.clearOssKeys.disabled = true;
  els.configStatus.classList.remove("error-text");
  els.configStatus.textContent = "正在清空 OSS Key...";

  try {
    await fetchJSON("/api/config", {
      method: "POST",
      body: JSON.stringify({
        clearOssKeys: true,
        workspaceId: els.configWorkspace.value.trim(),
        region: els.configRegion.value.trim(),
        baseURL: els.configBaseUrl.value.trim(),
        visionModel: els.configVisionModel.value.trim(),
        omniModel: els.configOmniModel.value.trim(),
        ossRegion: els.configOssRegion.value.trim(),
        ossBucket: els.configOssBucket.value.trim(),
        ossEndpoint: els.configOssEndpoint.value.trim(),
        ossPrefix: els.configOssPrefix.value.trim(),
        ossSignedUrlExpires: Number(els.configOssExpires.value || 86400)
      })
    });
    await loadConfig();
    els.configStatus.textContent = "OSS Key 已清空";
  } catch (error) {
    els.configStatus.textContent = error.message;
    els.configStatus.classList.add("error-text");
  } finally {
    els.clearOssKeys.disabled = false;
  }
}

async function clearSavedGithubToken() {
  els.clearGithubToken.disabled = true;
  els.configStatus.classList.remove("error-text");
  els.configStatus.textContent = "正在清空 GitHub Token...";

  try {
    await fetchJSON("/api/config", {
      method: "POST",
      body: JSON.stringify({
        clearGithubToken: true,
        workspaceId: els.configWorkspace.value.trim(),
        region: els.configRegion.value.trim(),
        baseURL: els.configBaseUrl.value.trim(),
        visionModel: els.configVisionModel.value.trim(),
        omniModel: els.configOmniModel.value.trim(),
        ossRegion: els.configOssRegion.value.trim(),
        ossBucket: els.configOssBucket.value.trim(),
        ossEndpoint: els.configOssEndpoint.value.trim(),
        ossPrefix: els.configOssPrefix.value.trim(),
        ossSignedUrlExpires: Number(els.configOssExpires.value || 86400),
        githubOwner: els.configGithubOwner.value.trim(),
        githubRepo: els.configGithubRepo.value.trim(),
        githubReleaseTag: els.configGithubReleaseTag.value.trim(),
        githubReleaseName: els.configGithubReleaseName.value.trim(),
        githubAssetPrefix: els.configGithubAssetPrefix.value.trim()
      })
    });
    await loadConfig();
    els.configStatus.textContent = "GitHub Token 已清空";
  } catch (error) {
    els.configStatus.textContent = error.message;
    els.configStatus.classList.add("error-text");
  } finally {
    els.clearGithubToken.disabled = false;
  }
}

async function runDemo() {
  const data = await fetchJSON("/api/analyze", {
    method: "POST",
    body: JSON.stringify({
      title: els.title.value,
      demoMode: true
    })
  });
  if (els.videoUrl.value.trim() || state.localVideoName) return;
  state.report = data.report;
  renderReport();
}

async function runAnalysis() {
  await loadHealth();

  const payload = {
    videoUrl: els.videoUrl.value.trim(),
    videoDataUrl: state.localVideoDataUrl,
    uploadId: state.uploadId,
    videoFileName: state.localVideoName,
    videoDuration: Number.isFinite(els.sourcePreview.duration) ? els.sourcePreview.duration : 0,
    title: els.title.value.trim(),
    fps: Number(els.fps.value),
    analysisMode: state.uploadId ? "vision" : els.analysisMode.value,
    subtitleText: els.subtitleText.value.trim(),
    prompt: els.prompt.value.trim()
  };

  if (state.localVideoTooLarge) {
    setProgress("本地路径模式限制视频本身不超过 100MB。请压缩视频或改用 OSS/公网 URL。", "error");
    return;
  }

  if (state.health?.configured && !payload.videoUrl && !payload.videoDataUrl && !payload.uploadId) {
    setProgress("请先填写公网视频 URL，或上传一个不超过 100MB 的本地视频文件。", "error");
    return;
  }

  els.runAnalysis.disabled = true;
  const modeLabel = state.uploadId ? "DashScope 本地路径视频理解模型" : (payload.analysisMode === "omni" ? "声音/对白专精模型" : "视频理解主力模型");
  setProgress(state.health?.configured ? `正在提交给阿里云${modeLabel}...` : "正在生成演示报告...");

  try {
    const data = await fetchJSON("/api/analyze", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    state.report = data.report;
    renderReport();
    setProgress(data.mode === "api" ? "分析完成" : data.note || "演示报告已生成");
  } catch (error) {
    setProgress(error.message, "error");
  } finally {
    els.runAnalysis.disabled = false;
  }
}

function updateVideoPreview() {
  const url = els.videoUrl.value.trim();
  if (!url) {
    if (state.localVideoObjectUrl) {
      els.sourcePreview.src = state.localVideoObjectUrl;
      els.sourcePreview.style.display = "block";
      els.emptyPreview.style.display = "none";
    } else {
      els.sourcePreview.removeAttribute("src");
      els.sourcePreview.style.display = "none";
      els.emptyPreview.style.display = "grid";
    }
    return;
  }

  els.sourcePreview.src = url;
  els.sourcePreview.style.display = "block";
  els.emptyPreview.style.display = "none";
}

async function handleVideoFile() {
  const file = els.videoFile.files?.[0];
  state.localVideoDataUrl = "";
  state.localVideoName = "";
  state.localVideoTooLarge = false;
  state.uploadId = "";

  if (state.localVideoObjectUrl) {
    URL.revokeObjectURL(state.localVideoObjectUrl);
    state.localVideoObjectUrl = "";
  }

  if (!file) {
    updateVideoPreview();
    return;
  }

  if (!file.type.startsWith("video/")) {
    setProgress("请选择 video/* 类型的视频文件。", "error");
    els.videoFile.value = "";
    updateVideoPreview();
    return;
  }

  state.localVideoName = file.name;
  state.localVideoObjectUrl = URL.createObjectURL(file);
  updateVideoPreview();

  if (els.uploadMode.value === "oss") {
    const ossLimit = 2 * 1024 * 1024 * 1024;
    if (file.size > ossLimit) {
      setProgress(`已选择 ${file.name}，但当前 OSS 上传限制 2GB。请先压缩或分片上传。`, "error");
      return;
    }

    els.videoFile.disabled = true;
    setProgress(`正在上传到 OSS：${file.name}`);
    try {
      const uploaded = await uploadVideoToOSS(file);
      state.uploadId = "";
      state.localVideoDataUrl = "";
      els.videoUrl.value = uploaded.videoUrl;
      updateVideoPreview();
      setProgress(`OSS 上传完成，签名 URL 有效 ${uploaded.expires} 秒。现在可以直接开始分析。`);
    } catch (error) {
      setProgress(error.message, "error");
    } finally {
      els.videoFile.disabled = false;
    }
    return;
  }

  if (els.uploadMode.value === "github") {
    const githubLimit = 2 * 1024 * 1024 * 1024;
    if (file.size > githubLimit) {
      setProgress(`已选择 ${file.name}，但 GitHub Release asset 建议不超过 2GB。`, "error");
      return;
    }

    els.videoFile.disabled = true;
    setProgress(`正在上传到 GitHub Releases：${file.name}`);
    try {
      const uploaded = await uploadVideoToGitHub(file);
      state.uploadId = "";
      state.localVideoDataUrl = "";
      els.videoUrl.value = uploaded.videoUrl;
      updateVideoPreview();
      setProgress("GitHub Release 上传完成，下载 URL 已填入。现在可以开始分析。");
    } catch (error) {
      setProgress(error.message, "error");
    } finally {
      els.videoFile.disabled = false;
    }
    return;
  }

  const localPathLimit = 100 * 1024 * 1024;

  if (file.size > localPathLimit) {
    state.localVideoTooLarge = true;
    setProgress(`已选择 ${file.name}，但本地路径模式限制 100MB。请压缩视频或改用 OSS/公网 URL。`, "error");
    return;
  }

  els.videoFile.disabled = true;
  setProgress(`正在上传到本地路径模式：${file.name}`);

  try {
    const uploaded = await uploadLocalVideo(file);
    state.uploadId = uploaded.uploadId;
    els.analysisMode.value = "vision";
    setProgress(`已保存本地路径：${file.name}。将使用视频理解模型分析；如需声音理解，请改用 OSS/公网 URL + 声音/对白专精模式。`);
  } catch (error) {
    state.uploadId = "";
    setProgress(error.message, "error");
  } finally {
    els.videoFile.disabled = false;
  }
}

async function uploadLocalVideo(file) {
  const response = await fetch("/api/upload", {
    method: "POST",
    headers: {
      "Content-Type": file.type || "video/mp4",
      "X-File-Name": encodeURIComponent(file.name)
    },
    body: file
  });

  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `上传失败：${response.status}`);
  return data;
}

async function uploadVideoToOSS(file) {
  const response = await fetch("/api/oss/upload", {
    method: "POST",
    headers: {
      "Content-Type": file.type || "video/mp4",
      "X-File-Name": encodeURIComponent(file.name)
    },
    body: file
  });

  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `OSS 上传失败：${response.status}`);
  return data;
}

async function uploadVideoToGitHub(file) {
  const response = await fetch("/api/github/upload", {
    method: "POST",
    headers: {
      "Content-Type": file.type || "video/mp4",
      "X-File-Name": encodeURIComponent(file.name)
    },
    body: file
  });

  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `GitHub 上传失败：${response.status}`);
  return data;
}

function renderReport() {
  const report = state.report;
  if (!report) return;

  const meta = report.meta || {};
  els.reportTitle.textContent = meta.title || "逐镜拉片报告";
  els.reportSubtitle.textContent = `${meta.duration || "片长待识别"} · ${meta.sceneCount || 0} 场景 · ${meta.shotCount || report.shots.length} 镜 · ${meta.basis || "视觉理解分析"}`;
  els.sceneCount.textContent = meta.sceneCount || report.scenes?.length || 0;
  els.shotCount.textContent = meta.shotCount || report.shots?.length || 0;
  els.basis.textContent = String(meta.basis || "视觉").slice(0, 12);

  renderSceneFilter();
  updateVideoPreview();
  renderRows();
}

function renderSceneFilter() {
  const current = els.sceneFilter.value;
  const scenes = unique((state.report?.shots || []).map(shot => shot.scene).filter(Boolean));
  els.sceneFilter.innerHTML = `<option value="">全部</option>${scenes.map(scene => `<option value="${escapeHTML(scene)}">${escapeHTML(scene)}</option>`).join("")}`;
  els.sceneFilter.value = scenes.includes(current) ? current : "";
}

function renderRows() {
  const report = state.report;
  if (!report) return;

  const q = els.search.value.trim().toLowerCase();
  const scene = els.sceneFilter.value;
  const rows = (report.shots || []).filter(shot => {
    if (scene && shot.scene !== scene) return false;
    if (!q) return true;
    return Object.values(shot).join(" ").toLowerCase().includes(q);
  });

  els.shotRows.innerHTML = rows.map(shot => renderShotRow(shot, report.videoUrl)).join("");
  setProgress(`当前显示 ${rows.length} / ${(report.shots || []).length} 个镜头`);
}

function renderShotRow(shot, videoUrl) {
  const frameUrl = videoUrl
    ? `/api/frame?videoUrl=${encodeURIComponent(videoUrl)}&time=${encodeURIComponent(shot.start || shot.timecode || 0)}`
    : "";
  return `
    <tr>
      <td>
        <div class="shot-thumb">
          ${frameUrl
            ? `<img src="${frameUrl}" alt="${escapeHTML(shot.shot)} 截图" loading="lazy" onerror="this.remove(); this.parentElement.insertAdjacentHTML('beforeend','<div class=&quot;shot-fallback&quot;>${escapeHTML(shot.timecode || "")}</div>')">`
            : `<div class="shot-fallback">${escapeHTML(shot.timecode || "")}</div>`}
        </div>
      </td>
      <td><span class="shot-label">${escapeHTML(shot.shot || "")}</span></td>
      <td>${escapeHTML(shot.timecode || "")}</td>
      <td><span class="tag">${escapeHTML(shot.shotSize || "")}</span></td>
      <td>${escapeHTML(shot.camera || "")}</td>
      <td>${escapeHTML(shot.visual || "")}</td>
      <td>${escapeHTML(shot.audio || "")}</td>
      <td>${escapeHTML(shot.analysis || "")}</td>
    </tr>
  `;
}

function exportMarkdown() {
  if (!state.report) return;
  const report = state.report;
  const meta = report.meta || {};
  const lines = [
    `# ${meta.title || "逐镜拉片报告"}`,
    "",
    `- 片长：${meta.duration || "待识别"}`,
    `- 场景：${meta.sceneCount || 0}`,
    `- 镜头：${meta.shotCount || report.shots.length}`,
    `- 分析依据：${meta.basis || ""}`,
    "",
    "| 镜号 | 时间码 | 景别 | 镜头运动 | 画面内容 / 人物动作 | 声音 / 音乐 | 分析注释 |",
    "|---|---|---|---|---|---|---|"
  ];

  for (const shot of report.shots || []) {
    lines.push(`| ${cell(shot.shot)} | ${cell(shot.timecode)} | ${cell(shot.shotSize)} | ${cell(shot.camera)} | ${cell(shot.visual)} | ${cell(shot.audio)} | ${cell(shot.analysis)} |`);
  }

  downloadText(`${filename(meta.title)}.md`, lines.join("\n"), "text/markdown;charset=utf-8");
}

function exportCsv() {
  if (!state.report) return;
  const headers = ["镜号", "场景", "时间码", "景别", "镜头运动", "画面内容 / 人物动作", "声音 / 音乐", "分析注释"];
  const rows = (state.report.shots || []).map(shot => [
    shot.shot,
    shot.scene,
    shot.timecode,
    shot.shotSize,
    shot.camera,
    shot.visual,
    shot.audio,
    shot.analysis
  ]);
  const csv = [headers, ...rows].map(row => row.map(csvCell).join(",")).join("\n");
  downloadText(`${filename(state.report.meta?.title)}.csv`, `\ufeff${csv}`, "text/csv;charset=utf-8");
}

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed: ${response.status}`);
  return data;
}

function setProgress(message, kind = "normal") {
  els.progressLine.textContent = message;
  els.progressLine.className = "progress-line";
  if (kind === "error") els.progressLine.classList.add("error-text");
  if (kind === "warn") els.progressLine.style.color = "var(--gold)";
  else els.progressLine.style.color = "";
}

function unique(items) {
  return [...new Set(items)];
}

function escapeHTML(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function cell(value) {
  return String(value ?? "").replaceAll("|", "\\|").replaceAll("\n", "<br>");
}

function csvCell(value) {
  return `"${String(value ?? "").replaceAll('"', '""')}"`;
}

function filename(value) {
  return String(value || "shot-report")
    .replace(/[\\/:*?"<>|]/g, "")
    .replace(/\s+/g, "-")
    .slice(0, 80) || "shot-report";
}

function downloadText(name, content, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
