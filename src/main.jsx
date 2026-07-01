import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const DESKTOP_API_BASE = "http://127.0.0.1:32176";
const configuredApiBase = import.meta.env.VITE_API_BASE;
const API_BASE =
  typeof configuredApiBase === "string"
    ? configuredApiBase.replace(/\/$/, "")
    : import.meta.env.DEV
      ? ""
      : DESKTOP_API_BASE;
const API_LABEL = (API_BASE || "Vite proxy /api").replace(/^https?:\/\//, "");

const emptyReport = {
  meta: {
    title: "样例短片 · 逐镜拉片报告",
    duration: "片长待识别",
    sceneCount: 0,
    shotCount: 0,
    basis: "等待分析",
  },
  shots: [],
};

const demoShots = [
  {
    shot: "SHOT-001",
    timecode: "00:00:00-00:00:06",
    shotSize: "全景",
    camera: "固定",
    visual: "城市清晨，主角推门走出公寓，街道空旷。",
    audio: "环境底噪 + 低频 pad",
    analysis: "建立空间，冷色调铺陈孤独感。",
  },
  {
    shot: "SHOT-002",
    timecode: "00:00:06-00:00:11",
    shotSize: "中景",
    camera: "缓推",
    visual: "主角整理衣领，目光投向画面外。",
    audio: "脚步声 + 渐入弦乐",
    analysis: "推镜强调心理压力，注意力收束。",
  },
  {
    shot: "SHOT-003",
    timecode: "00:00:11-00:00:15",
    shotSize: "特写",
    camera: "手持",
    visual: "手指敲击桌面，节奏逐渐加快。",
    audio: "鼓点节拍 · 无对白",
    analysis: "手持制造不安，剪辑提速。",
  },
  {
    shot: "SHOT-004",
    timecode: "00:00:15-00:00:22",
    shotSize: "近景",
    camera: "横摇",
    visual: "对话开始，反打两位人物。",
    audio: "对白 + 室内混响",
    analysis: "正反打建立对峙关系。",
  },
];

function App() {
  const [tab, setTab] = useState("analysis");
  const [drawer, setDrawer] = useState("setup");
  const [status, setStatus] = useState("CODEX 检测中");
  const [health, setHealth] = useState(null);
  const [codexStatus, setCodexStatus] = useState(null);
  const [job, setJob] = useState(null);
  const [settings, setSettings] = useState({});
  const [report, setReport] = useState(emptyReport);
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("");
  const [form, setForm] = useState({
    videoUrl: "",
    title: "逐镜拉片报告",
    fps: "1",
    analysisMode: "codex",
    uploadMode: "local",
    subtitleText: "",
    customPrompt: "",
  });
  const [file, setFile] = useState(null);

  useEffect(() => {
    let cancelled = false;
    async function bootRuntime() {
      for (let attempt = 0; attempt < 18 && !cancelled; attempt += 1) {
        const healthOk = await refreshHealth({ booting: true });
        const codexOk = await refreshCodexStatus({ booting: true });
        if (healthOk) loadSettings();
        if (healthOk && codexOk) return;
        await sleep(900 + Math.min(attempt, 6) * 350);
      }
    }
    bootRuntime();
    return () => {
      cancelled = true;
    };
  }, []);

  const hasReport = Boolean(report.shots?.length);
  const shots = hasReport ? report.shots : demoShots;
  const meta = report.meta || emptyReport.meta;
  const shownShots = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return shots;
    return shots.filter((shot) =>
      Object.values(shot).join(" ").toLowerCase().includes(q),
    );
  }, [shots, filter]);

  async function refreshHealth(options = {}) {
    try {
      const data = await request("/api/health");
      setHealth(data);
      setStatus(data.codexAvailable ? "Codex CLI 已检测，正在确认登录" : "未检测到 Codex CLI");
      return true;
    } catch (error) {
      setStatus(options.booting ? "本地 daemon 启动中，正在重试" : "本地后端未连接");
      return false;
    }
  }

  async function refreshCodexStatus(options = {}) {
    try {
      const data = await request("/api/codex/status");
      setCodexStatus(data);
      setStatus(data.ready ? "CODEX 已就绪" : data.message || "Codex 不可用");
      return true;
    } catch (error) {
      setCodexStatus({
        ready: false,
        installed: null,
        authenticated: null,
        status: "backend-starting",
        message: options.booting
          ? "本地 daemon 正在启动或连接中，Shot Reader 会自动重试。"
          : `本地后端未连接：${error.message}`,
      });
      setStatus(options.booting ? "本地 daemon 启动中，正在重试" : `Codex 检测失败：${error.message}`);
      return false;
    }
  }

  async function loadSettings() {
    try {
      setSettings(await request("/api/config"));
    } catch {
      setSettings({});
    }
  }

  function updateForm(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function runAnalyze() {
    setDrawer("result");
    setBusy(true);
    setJob(null);
    setStatus(form.analysisMode === "codex" ? "正在创建 Codex 分析任务" : "正在分析视频");
    const body = new FormData();
    body.set("mode", form.uploadMode);
    body.set("title", form.title);
    body.set("video_url", form.videoUrl);
    body.set("analysis_mode", form.analysisMode);
    body.set("fps", form.fps);
    body.set("subtitle_text", form.subtitleText);
    body.set("custom_prompt", form.customPrompt);
    if (file) body.set("file", file);
    try {
      if (form.analysisMode === "codex") {
        const created = await request("/api/codex/analyze", { method: "POST", body });
        setJob(created);
        setStatus(created.message || "Codex 任务已创建");
        const done = await pollJob(created.id);
        setReport(done.report);
        setStatus(`Codex 分析完成：${done.report?.shots?.length || 0} 镜`);
      } else {
        const data = await request("/api/analyze", { method: "POST", body });
        setReport(data.report);
        setStatus(`分析完成：${data.report?.shots?.length || 0} 镜`);
      }
    } catch (error) {
      setStatus(`错误：${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function pollJob(jobId) {
    for (;;) {
      await sleep(1500);
      const data = await request(`/api/jobs/${jobId}`);
      setJob(data);
      setStatus(data.message || `Codex 任务状态：${data.status}`);
      if (data.status === "completed") return data;
      if (data.status === "failed") throw new Error(data.error || data.message || "Codex 分析失败");
    }
  }

  async function uploadGithub() {
    if (!file) {
      setStatus("请先选择本地视频");
      return;
    }
    setBusy(true);
    setStatus("正在上传 GitHub Release");
    const body = new FormData();
    body.set("file", file);
    try {
      const data = await request("/api/upload/github", { method: "POST", body });
      updateForm("videoUrl", data.url);
      updateForm("uploadMode", "url");
      setStatus("GitHub URL 已填入");
    } catch (error) {
      setStatus(`上传失败：${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function saveSettings() {
    setBusy(true);
    setStatus("正在保存配置");
    try {
      const data = await request("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      setSettings(data);
      setStatus("配置已保存");
      refreshHealth();
      refreshCodexStatus();
    } catch (error) {
      setStatus(`保存失败：${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  function exportMarkdown() {
    if (!report.shots?.length) return;
    const lines = [
      `# ${meta.title || "逐镜拉片报告"}`,
      "",
      `- 片长：${meta.duration || ""}`,
      `- 场景数：${meta.sceneCount || 0}`,
      `- 镜头数：${meta.shotCount || report.shots.length}`,
      `- 分析依据：${meta.basis || ""}`,
      "",
      "| 镜号 | 时间码 | 景别 | 镜头运动 | 画面内容 / 人物动作 | 分析注释 | 声音 / 音乐 |",
      "|---|---|---|---|---|---|---|",
      ...report.shots.map((shot) =>
        [
          shot.shot,
          shot.timecode,
          shot.shotSize,
          shot.camera,
          shot.visual,
          shot.analysis,
          shot.audio,
        ]
          .map((value) => String(value || "").replaceAll("|", "\\|"))
          .join(" | "),
      ).map((row) => `| ${row} |`),
    ];
    downloadText(`${meta.title || "shot-report"}.md`, lines.join("\n"), "text/markdown");
  }

  function exportCsv() {
    if (!report.shots?.length) return;
    const header = ["镜号", "时间码", "景别", "镜头运动", "画面内容 / 人物动作", "分析注释", "声音 / 音乐"];
    const rows = report.shots.map((shot) => [
      shot.shot,
      shot.timecode,
      shot.shotSize,
      shot.camera,
      shot.visual,
      shot.analysis,
      shot.audio,
    ]);
    const csv = [header, ...rows]
      .map((row) => row.map((cell) => `"${String(cell || "").replaceAll('"', '""')}"`).join(","))
      .join("\n");
    downloadText(`${meta.title || "shot-report"}.csv`, `\ufeff${csv}`, "text/csv");
  }

  return (
    <div className="shell">
      <div className="app">
        <Sidebar tab={tab} setTab={setTab} status={status} health={health} codexStatus={codexStatus} />
        <Spine form={form} status={status} health={health} report={report} codexStatus={codexStatus} />
        <main className="main">
          {tab === "analysis" && (
            <AnalysisPage
              drawer={drawer}
              setDrawer={setDrawer}
              form={form}
              updateForm={updateForm}
              file={file}
              setFile={setFile}
              report={report}
              meta={meta}
              shots={shownShots}
              totalShots={shots.length}
              hasReport={hasReport}
              isDemo={!hasReport}
              busy={busy}
              status={status}
              codexStatus={codexStatus}
              job={job}
              filter={filter}
              setFilter={setFilter}
              onAnalyze={runAnalyze}
              onUploadGithub={uploadGithub}
              onExportMarkdown={exportMarkdown}
              onExportCsv={exportCsv}
            />
          )}
          {tab === "library" && <LibraryPage setTab={setTab} report={report} onExportMarkdown={exportMarkdown} onExportCsv={exportCsv} />}
          {tab === "prompts" && <PromptsPage />}
          {tab === "settings" && <SettingsPage settings={settings} setSettings={setSettings} onSave={saveSettings} onRefresh={loadSettings} codexStatus={codexStatus} onRefreshCodex={refreshCodexStatus} />}
        </main>
      </div>
    </div>
  );
}

function Sidebar({ tab, setTab, status, health, codexStatus }) {
  return (
    <aside className="rail">
      <div className="rail-wm">
        逐镜<br />拉片<span className="en">SHOT READER</span>
      </div>
      <nav className="rail-nav">
        <button type="button" aria-current={tab === "analysis" ? "page" : undefined} className={tab === "analysis" ? "on" : ""} onClick={() => setTab("analysis")}>分析任务</button>
        <button type="button" aria-current={tab === "library" ? "page" : undefined} className={tab === "library" ? "on" : ""} onClick={() => setTab("library")}>报告库</button>
        <button type="button" aria-current={tab === "prompts" ? "page" : undefined} className={tab === "prompts" ? "on" : ""} onClick={() => setTab("prompts")}>提示词</button>
        <button type="button" aria-current={tab === "settings" ? "page" : undefined} className={tab === "settings" ? "on" : ""} onClick={() => setTab("settings")}>设置与运行时</button>
      </nav>
      <div className="rail-stat">
        <div className="v"><i />{status}</div>
        <p>{runtimeLabel(health, codexStatus)}<br />本地 daemon<br />{API_LABEL}</p>
      </div>
    </aside>
  );
}

function Spine({ form, status, health, report, codexStatus }) {
  const shotCount = String(report?.shots?.length || 0).padStart(2, "0");
  const sceneCount = String(report?.meta?.sceneCount || 0).padStart(2, "0");
  const items = [
    `● ${status}`,
    `MODEL ${analysisModelLabel(form.analysisMode, health, codexStatus)}`,
    `FPS ${Number(form.fps || 1).toFixed(1)}`,
    `模式 ${analysisModeLabel(form.analysisMode)}`,
    `上传 ${uploadLabel(form.uploadMode)}`,
    `就绪 ${sceneCount} / ${shotCount}`,
  ];
  return (
    <div className="spine">
      <div className="trk">
        {[...items, ...items].map((item, index) => (
          <span key={`${item}-${index}`}>{item}</span>
        ))}
      </div>
    </div>
  );
}

function AnalysisPage(props) {
  const {
    drawer,
    setDrawer,
    form,
    updateForm,
    file,
    setFile,
    meta,
    shots,
    totalShots,
    hasReport,
    isDemo,
    busy,
    status,
    codexStatus,
    job,
    filter,
    setFilter,
    onAnalyze,
    onUploadGithub,
    onExportMarkdown,
    onExportCsv,
  } = props;
  const sceneCount = meta.sceneCount || 0;
  return (
    <>
      <Header
        eyebrow="No.06 / SHOT-BY-SHOT DOSSIER"
        title="视频识别 Agent · 逐镜拉片"
        actions={
          <>
            <button className="obtn" disabled={!hasReport || busy} onClick={onExportMarkdown}>导出 MD</button>
            <button className="obtn" disabled={!hasReport || busy} onClick={onExportCsv}>导出 CSV</button>
            <button className="obtn run" disabled={busy} onClick={onAnalyze}>{busy ? "分析中..." : "开始分析 →"}</button>
          </>
        }
      />
      <div className="stage">
        <section className={`drawer dw-setup ${drawer === "setup" ? "active" : ""}`}>
          <button className="dwh" onClick={() => setDrawer("setup")}>
            <span className="no">1</span>输入设置 · SETUP<span className="gap" /><span className="hint">配置视频与分析参数</span>
          </button>
          <div className="dwbody">
            <div className="cover">
              <div className="cv-l">
                <p className="ek">ANALYSIS BRIEF</p>
                <h3>{meta.title || form.title}</h3>
                <p>{meta.basis || "基于逐秒截帧的视听语言分析。景别、镜头运动、声音与剪辑注释逐镜成表，可导出 Markdown 与 CSV。"}</p>
                <div className="cv-mtr">
                  <div><b>{String(sceneCount).padStart(2, "0")}</b><span>场景</span></div>
                  <div><b className="ac">{String(totalShots).padStart(2, "0")}</b><span>镜头</span></div>
                  <div><b>{busy ? "LIVE" : "READY"}</b><span>分析依据</span></div>
                </div>
              </div>
              <div className="frame">
                <span className="brk tl" /><span className="brk tr" /><span className="brk bl" /><span className="brk br" />
                <span className="l">{file?.name || form.videoUrl || "▶ 等待视频 URL"}</span>
              </div>
            </div>
            <div className={`status-strip ${busy ? "live" : ""}`}>
              <span className="led" />
              <strong>{busy ? "ANALYZING" : hasReport ? "REPORT READY" : "READY"}</strong>
              <span>{status}</span>
              <span className="right">{analysisModeLabel(form.analysisMode)} · {uploadLabel(form.uploadMode)}</span>
            </div>
            {form.analysisMode === "codex" && (
              <div className={`agent-card ${codexStatus?.ready ? "ok" : "warn"}`}>
                <div>
                  <p className="ek">CODEX AGENT MODE</p>
                  <h4>{codexStatus?.ready ? "Codex 本地运行时已就绪" : "等待 Codex 运行时"}</h4>
                  <p>{codexStatus?.message || "将使用本机 Codex 登录状态、关键帧图片和本地任务目录生成逐镜报告。"}</p>
                </div>
                <div className="agent-meter">
                  <span>{codexStatus?.version || "Codex CLI"}</span>
                  <span>{codexStatus?.authMode || "login"}</span>
                  <span>{codexStatus?.model || "默认模型"}</span>
                  <span>{reasoningEffortLabel(codexStatus?.reasoningEffort)}</span>
                </div>
              </div>
            )}
            <div className="form">
              <Field span="s3" label="视频公网 URL"><input className="inp" value={form.videoUrl} onChange={(e) => updateForm("videoUrl", e.target.value)} placeholder="https://example.com/clip.mp4" /></Field>
              <Field span="s2" label="报告标题"><input className="inp" value={form.title} onChange={(e) => updateForm("title", e.target.value)} /></Field>
              <Field label="抽帧 FPS"><select className="sel" value={form.fps} onChange={(e) => updateForm("fps", e.target.value)}><option>0.2</option><option>0.5</option><option>1</option><option>2</option></select></Field>
              <Field span="s2" label="分析模式"><select className="sel" value={form.analysisMode} onChange={(e) => updateForm("analysisMode", e.target.value)}><option value="codex">Codex Agent（本地登录）</option><option value="vision">旧模式：视频理解主力（qwen3.7-plus）</option><option value="omni">旧模式：声音/对白专精（qwen3.5-omni-plus）</option></select></Field>
              <Field span="s2" label="上传方式"><select className="sel" value={form.uploadMode} onChange={(e) => updateForm("uploadMode", e.target.value)}><option value="local">本地路径 · 100MB</option><option value="github">GitHub Releases</option><option value="url">公网 URL</option></select></Field>
              <Field span="s2" label="本地文件">
                <div className="file-row">
                  <input className="inp file" type="file" accept="video/*" onChange={(e) => setFile(e.target.files?.[0] || null)} />
                  <button className="mini" type="button" onClick={onUploadGithub}>上传 GitHub</button>
                </div>
              </Field>
              <Field span="s3" label="字幕 / 音轨转写"><textarea className="txa" value={form.subtitleText} onChange={(e) => updateForm("subtitleText", e.target.value)} placeholder="粘贴字幕或转写" /></Field>
              <Field span="s3" label="补充分析要求"><textarea className="txa" value={form.customPrompt} onChange={(e) => updateForm("customPrompt", e.target.value)} placeholder="例如：重点分析镜头运动与叙事转折" /></Field>
            </div>
          </div>
        </section>
        <section className={`drawer dw-result ${drawer === "result" ? "active open" : ""}`}>
          <button className="dwh" onClick={() => setDrawer("result")}>
            <span className="no">2</span>逐镜结果 · RESULT<span className="gap" /><span className="hint">{totalShots} 镜头 / {sceneCount} 场景 · 点击展开</span><span className="ar">▲</span>
          </button>
          <div className="dwbody">
            <div className="ttools">
              <div className="l"><span className="otag acid">逐镜表格</span><span className="otag">{isDemo ? "样例数据" : `${totalShots} 镜头`}</span><span className="otag">{sceneCount} 场景</span></div>
              <input className="filter" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="筛选镜头、画面、注释" />
            </div>
            {busy && <div className="busybar"><span />{job?.message || "正在等待 Agent 返回结构化逐镜结果"}</div>}
            <ShotTable shots={shots} isDemo={isDemo} />
          </div>
        </section>
      </div>
    </>
  );
}

function ShotTable({ shots, isDemo }) {
  return (
    <div className="tabscroll">
      <table className="rtab">
        <colgroup>
          <col className="c-thumb" />
          <col className="c-shot" />
          <col className="c-time" />
          <col className="c-size" />
          <col className="c-camera" />
          <col className="c-visual" />
          <col className="c-analysis" />
          <col className="c-audio" />
        </colgroup>
        <thead>
          <tr>
            <th>截图</th><th>镜号</th><th>时间码</th><th>景别</th><th>镜头运动</th><th>画面内容 / 人物动作</th><th>分析注释</th><th>声音 / 音乐</th>
          </tr>
        </thead>
        <tbody>
          {shots.map((shot, index) => (
            <tr key={`${shot.shot || index}-${shot.timecode || index}`}>
              <td className="thumb-cell">
                {shot.thumbnailUrl ? (
                  <img className="thumb-img" src={`${API_BASE}${shot.thumbnailUrl}`} alt={shot.shot || "shot"} />
                ) : (
                  <div className={`thumb ${isDemo ? "demo" : "missing"}`}><span>▶</span><em>{isDemo ? "SAMPLE" : "NO FRAME"}</em></div>
                )}
              </td>
              <td className="shotno">{shot.shot || `镜 ${index + 1}`}</td>
              <td className="nw">{shot.timecode}</td>
              <td className="nw">{shot.shotSize}</td>
              <td className="nw">{shot.camera}</td>
              <td>{shot.visual}</td>
              <td>{shot.analysis}</td>
              <td>{shot.audio}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Header({ eyebrow, title, actions }) {
  return (
    <div className="dh">
      <div><p className="idx">{eyebrow}</p><h2>{title}</h2></div>
      <div className="tools">{actions}</div>
    </div>
  );
}

function Field({ label, span = "", children }) {
  return <div className={`cell ${span}`}><label className="fld-l">{label}</label>{children}</div>;
}

function LibraryPage({ setTab, report, onExportMarkdown, onExportCsv }) {
  const hasReport = Boolean(report?.shots?.length);
  return (
    <>
      <Header eyebrow="No.07 / SAVED REPORTS" title="报告库" actions={<><button className="obtn" onClick={onExportMarkdown}>导出 MD</button><button className="obtn" onClick={onExportCsv}>导出 CSV</button></>} />
      <div className="body560">
        <div className="empty">
          <p className="ek">{hasReport ? "CURRENT · 01 ITEM" : "EMPTY · 00 ITEMS"}</p>
          <h3>{hasReport ? report.meta?.title || "当前报告" : "还没有已保存的报告"}</h3>
          <p>{hasReport ? `${report.meta?.sceneCount || 0} 场景 · ${report.shots.length} 镜 · ${report.meta?.basis || "视觉理解分析"}` : "每次分析完成后会归档到这里，可按标题、模型、日期检索，并重新导出 Markdown / CSV。"}</p>
          <button className="obtn run" onClick={() => setTab("analysis")}>回到分析任务 →</button>
        </div>
      </div>
    </>
  );
}

function PromptsPage() {
  return (
    <>
      <Header eyebrow="No.08 / PROMPT PRESETS" title="提示词" actions={<button className="obtn run">新建预设 →</button>} />
      <div className="body560">
        <div className="panel">
          <div className="pp2">
            <div className="fld"><label className="fld-l">预设名称</label><input className="inp" defaultValue="电影学院 · 视听语言拉片" /></div>
            <div className="fld"><label className="fld-l">适用模型</label><select className="sel"><option>全模态</option><option>视觉</option></select></div>
          </div>
          <div className="fld prompt-box"><label className="fld-l">系统提示词</label><textarea className="txa tall" defaultValue="你是资深拉片分析师。请按逐镜结构输出：镜号、时间码、景别、镜头运动、画面内容与人物动作、声音/音乐、剪辑与叙事注释。语言精炼，术语准确。" /></div>
        </div>
      </div>
    </>
  );
}

function SettingsPage({ settings, setSettings, onSave, onRefresh, codexStatus, onRefreshCodex }) {
  function set(key, value) {
    setSettings((prev) => ({ ...prev, [key]: value }));
  }
  return (
    <>
      <Header eyebrow="No.09 / LOCAL RUNTIME" title="设置与运行时" actions={<><button className="obtn" onClick={onRefreshCodex}>检测 Codex</button><button className="obtn" onClick={onRefresh}>刷新配置</button><button className="obtn run" onClick={onSave}>保存配置</button></>} />
      <div className="body560">
        <div className="panel cfg">
          <div className={`runtime-card ${codexStatus?.ready ? "ok" : "warn"}`}>
            <div>
              <p className="ek">CODEX RUNTIME</p>
              <h3>{codexStatus?.ready ? "Codex 图形化工作台已就绪" : "Codex 暂不可用"}</h3>
              <p>{codexStatus?.message || "Shot Reader 会优先使用本机 Codex 登录状态运行分析任务，不需要在这里填写 OpenAI API Key。"}</p>
            </div>
            <div className="runtime-facts">
              <span>{installStateLabel(codexStatus)}</span>
              <span>{authStateLabel(codexStatus)}</span>
              <span>{codexStatus?.model || "默认模型"}</span>
              <span>{reasoningEffortLabel(codexStatus?.reasoningEffort)}</span>
              <span>{codexStatus?.version || "version unknown"}</span>
            </div>
          </div>
          <div className="cfg-div"><h4>Codex Agent 默认参数</h4><p>这里控制 Shot Reader 调用 Codex 时使用的模型和推理强度；留空则跟随你本机 Codex 的默认配置。</p></div>
          <div className="cfg-g2">
            <div className="fld">
              <label className="fld-l">Codex 模型</label>
              <input className="inp" list="codex-models" value={settings.codex_model || ""} onChange={(e) => set("codex_model", e.target.value)} placeholder={codexStatus?.model || "跟随 Codex 默认"} />
              <datalist id="codex-models">
                <option value="gpt-5.5" />
                <option value="gpt-5.4" />
                <option value="gpt-5.4-mini" />
              </datalist>
              <span className="fnote">可手动输入 Codex 支持的模型名</span>
            </div>
            <div className="fld">
              <label className="fld-l">推理强度</label>
              <select className="sel" value={settings.codex_reasoning_effort || ""} onChange={(e) => set("codex_reasoning_effort", e.target.value)}>
                <option value="">跟随 Codex 默认</option>
                <option value="minimal">minimal · 最快</option>
                <option value="low">low · 轻量</option>
                <option value="medium">medium · 平衡</option>
                <option value="high">high · 深度</option>
                <option value="xhigh">xhigh · 最强</option>
              </select>
              <span className="fnote">越高越慢，也更消耗额度</span>
            </div>
          </div>
          <div className="cfg-div"><h4>DashScope / GitHub 旧模式配置</h4><p>这些配置只用于旧的 Qwen API 模式和 GitHub Releases 临时 URL；Codex Agent 默认模式不会读取 OpenAI API Key。</p></div>
          <div className="fld"><label className="fld-l">DASHSCOPE_API_KEY</label><input className="inp" type="password" value={settings.dashscope_api_key || ""} onChange={(e) => set("dashscope_api_key", e.target.value)} placeholder={settings.dashscope_api_key_masked || "未保存"} /><span className="fnote">留空保存时会保留原值</span></div>
          <div className="cfg-g3">
            <ConfigInput label="Workspace ID" value={settings.workspace_id} onChange={(v) => set("workspace_id", v)} />
            <ConfigInput label="Region" value={settings.region} onChange={(v) => set("region", v)} />
            <ConfigInput label="兼容模式 Base URL" value={settings.dashscope_base_url} onChange={(v) => set("dashscope_base_url", v)} />
          </div>
          <div className="cfg-g2">
            <ConfigInput label="视觉模型" value={settings.vision_model} onChange={(v) => set("vision_model", v)} />
            <ConfigInput label="全模态模型" value={settings.omni_model} onChange={(v) => set("omni_model", v)} />
          </div>
          <div className="cfg-div"><h4>GitHub Releases 临时 URL</h4><p>上传为 Release asset，用 browser_download_url 作为视频公网地址。仓库建议 public。</p></div>
          <div className="cfg-g2">
            <div className="fld"><label className="fld-l">GitHub Token</label><input className="inp" type="password" value={settings.github_token || ""} onChange={(e) => set("github_token", e.target.value)} placeholder={settings.github_token_masked || "未保存"} /></div>
            <ConfigInput label="Owner" value={settings.github_owner} onChange={(v) => set("github_owner", v)} />
          </div>
          <div className="cfg-g3">
            <ConfigInput label="Repo" value={settings.github_repo} onChange={(v) => set("github_repo", v)} />
            <ConfigInput label="Release Tag" value={settings.github_release_tag} onChange={(v) => set("github_release_tag", v)} />
            <ConfigInput label="Asset Prefix" value={settings.github_asset_prefix} onChange={(v) => set("github_asset_prefix", v)} />
          </div>
          <div className="cfg-act"><button className="obtn run" onClick={onSave}>保存配置</button><button className="obtn" onClick={onRefresh}>刷新</button></div>
        </div>
      </div>
    </>
  );
}

function ConfigInput({ label, value = "", onChange }) {
  return <div className="fld"><label className="fld-l">{label}</label><input className="inp" value={value || ""} onChange={(e) => onChange(e.target.value)} /></div>;
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, options);
  } catch (error) {
    throw new Error(
      `本地后端未连接：请确认 Shot Reader.exe 与 backend-sidecar.exe 在同一目录，或没有安全软件拦截后端进程。详情：${error.message}`,
    );
  }
  const text = await response.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { detail: text };
  }
  if (!response.ok) {
    const detail = data.detail || data.message || response.statusText;
    const looksLikeStatic404 =
      response.status === 404 &&
      typeof detail === "string" &&
      /<!doctype html|<html|page not found|404/i.test(detail);
    if (looksLikeStatic404) {
      throw new Error(
        `后端 API 未连接：${API_LABEL} 返回了 404。新电脑上通常是本地后端没有启动，或端口被其他程序占用。请重新下载完整免安装包，确认 backend-sidecar.exe 没被安全软件删除。`,
      );
    }
    throw new Error(detail);
  }
  return data;
}

function downloadText(name, content, type) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name.replace(/[\\/:*?"<>|]/g, "_");
  a.click();
  URL.revokeObjectURL(url);
}

function uploadLabel(mode) {
  if (mode === "github") return "GitHub Releases";
  if (mode === "url") return "公网 URL";
  return "本地路径 · 100MB";
}

function analysisModeLabel(mode) {
  if (mode === "codex") return "Codex Agent · 本地运行时";
  if (mode === "omni") return "声音/对白专精";
  return "视频理解主力";
}

function analysisModelLabel(mode, health, codexStatus) {
  if (mode === "codex") return codexStatus?.model || "CODEX";
  if (mode === "omni") return health?.omniModel || "qwen3.5-omni-plus";
  return health?.visionModel || "qwen3.7-plus";
}

function runtimeLabel(health, codexStatus) {
  if (codexStatus?.ready) return `CODEX ${codexStatus.version || ""}`.trim();
  if (codexStatus?.status === "backend-starting") return "DAEMON 启动中";
  if (health?.codexAvailable) return "CODEX 待登录";
  return "CODEX 未安装";
}

function installStateLabel(codexStatus) {
  if (!codexStatus || codexStatus.installed == null) return "检测中";
  return codexStatus.installed ? "CLI 已安装" : "未安装 CLI";
}

function authStateLabel(codexStatus) {
  if (!codexStatus || codexStatus.authenticated == null) return "检测中";
  return codexStatus.authenticated ? "已登录" : "未登录";
}

function reasoningEffortLabel(value) {
  return value ? `推理 ${String(value).toUpperCase()}` : "默认推理";
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

createRoot(document.getElementById("root")).render(<App />);
