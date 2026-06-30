import ctypes
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from video_agent_core import (
    analyze_video,
    export_csv,
    export_markdown,
    get_config,
    mask_secret,
    save_config,
    upload_to_github_release,
)


FONT_FAMILY = "Microsoft YaHei UI"
COLORS = {
    "app": "#0b1020",
    "sidebar": "#0f172a",
    "panel": "#111827",
    "panel_alt": "#0f1629",
    "field": "#172033",
    "field_alt": "#111a2d",
    "border": "#263247",
    "border_soft": "#1d283a",
    "text": "#e5edf7",
    "muted": "#8fa1b7",
    "accent": "#38bdf8",
    "accent_hover": "#0ea5e9",
    "accent_soft": "#0b3147",
    "success": "#22c55e",
    "warning": "#fbbf24",
}

ANALYSIS_MODE_OPTIONS = {
    "全模态（画面 + 声音）": "omni",
    "视觉（仅画面）": "vision",
}


def enable_high_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


class VideoAgentApp(tk.Tk):
    def __init__(self):
        enable_high_dpi_awareness()
        super().__init__()
        self.title("视频识别 Agent GUI")
        self.geometry("1480x920")
        self.minsize(1180, 760)
        self.configure(bg=COLORS["app"])
        self._sync_tk_scaling()

        self.report = None
        self.tree_item_map = {}
        self.fields = {}
        self.page_buttons = {}
        self.local_file = tk.StringVar()
        self.video_url = tk.StringVar()
        self.status = tk.StringVar(value="就绪")
        self.report_title_var = tk.StringVar(value="等待分析")
        self.report_meta_var = tk.StringVar(value="选择视频、确认模型，然后开始生成逐镜报告。")

        self._build_style()
        self._build_ui()
        self.load_settings()
        self.show_page("workbench")

    def _sync_tk_scaling(self):
        try:
            scaling = self.winfo_fpixels("1i") / 72
            self.tk.call("tk", "scaling", scaling)
        except tk.TclError:
            pass

    def _build_style(self):
        self.option_add("*Font", (FONT_FAMILY, 10))
        self.style = ttk.Style(self)
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")

        self.style.configure(".", font=(FONT_FAMILY, 10))
        self.style.configure("App.TFrame", background=COLORS["app"])
        self.style.configure("Sidebar.TFrame", background=COLORS["sidebar"])
        self.style.configure("Panel.TFrame", background=COLORS["panel"])
        self.style.configure("Card.TFrame", background=COLORS["panel_alt"])
        self.style.configure("TLabel", background=COLORS["app"], foreground=COLORS["text"])
        self.style.configure("Panel.TLabel", background=COLORS["panel"], foreground=COLORS["text"])
        self.style.configure("Card.TLabel", background=COLORS["panel_alt"], foreground=COLORS["text"])
        self.style.configure("Muted.TLabel", background=COLORS["app"], foreground=COLORS["muted"])
        self.style.configure("PanelMuted.TLabel", background=COLORS["panel"], foreground=COLORS["muted"])
        self.style.configure("Sidebar.TLabel", background=COLORS["sidebar"], foreground=COLORS["text"])
        self.style.configure("SidebarMuted.TLabel", background=COLORS["sidebar"], foreground=COLORS["muted"])
        self.style.configure("PageTitle.TLabel", background=COLORS["app"], foreground=COLORS["text"], font=(FONT_FAMILY, 20, "bold"))
        self.style.configure("Title.TLabel", background=COLORS["panel"], foreground=COLORS["text"], font=(FONT_FAMILY, 14, "bold"))
        self.style.configure("SmallTitle.TLabel", background=COLORS["panel_alt"], foreground=COLORS["text"], font=(FONT_FAMILY, 11, "bold"))
        self.style.configure("Metric.TLabel", background=COLORS["panel_alt"], foreground=COLORS["accent"], font=(FONT_FAMILY, 18, "bold"))

        self.style.configure(
            "TEntry",
            fieldbackground=COLORS["field"],
            foreground=COLORS["text"],
            insertcolor=COLORS["text"],
            bordercolor=COLORS["border"],
            lightcolor=COLORS["border"],
            darkcolor=COLORS["border"],
            padding=8,
        )
        self.style.configure(
            "TCombobox",
            fieldbackground=COLORS["field"],
            background=COLORS["field"],
            foreground=COLORS["text"],
            arrowcolor=COLORS["accent"],
            bordercolor=COLORS["border"],
            lightcolor=COLORS["border"],
            darkcolor=COLORS["border"],
            padding=8,
        )
        self.style.map(
            "TCombobox",
            fieldbackground=[("readonly", COLORS["field"])],
            foreground=[("readonly", COLORS["text"])],
        )
        self.style.configure("TButton", padding=(12, 9), borderwidth=0, focusthickness=0)
        self.style.configure("Accent.TButton", background=COLORS["accent"], foreground="#06101f", font=(FONT_FAMILY, 10, "bold"))
        self.style.map("Accent.TButton", background=[("active", COLORS["accent_hover"])])
        self.style.configure("Ghost.TButton", background=COLORS["field"], foreground=COLORS["text"])
        self.style.map("Ghost.TButton", background=[("active", COLORS["border"])])
        self.style.configure("Nav.TButton", background=COLORS["sidebar"], foreground=COLORS["muted"], anchor="w", padding=(14, 10))
        self.style.configure("ActiveNav.TButton", background=COLORS["accent_soft"], foreground=COLORS["text"], anchor="w", padding=(14, 10))
        self.style.map("Nav.TButton", background=[("active", COLORS["field"])], foreground=[("active", COLORS["text"])])

        self.style.configure(
            "Report.Treeview",
            background=COLORS["panel"],
            fieldbackground=COLORS["panel"],
            foreground=COLORS["text"],
            rowheight=36,
            bordercolor=COLORS["border_soft"],
            borderwidth=0,
            font=(FONT_FAMILY, 10),
        )
        self.style.configure(
            "Report.Treeview.Heading",
            background=COLORS["field_alt"],
            foreground=COLORS["accent"],
            relief="flat",
            font=(FONT_FAMILY, 10, "bold"),
            padding=8,
        )
        self.style.map("Report.Treeview", background=[("selected", COLORS["accent_soft"])], foreground=[("selected", COLORS["text"])])
        self.style.configure("Vertical.TScrollbar", background=COLORS["field"], troughcolor=COLORS["panel"], bordercolor=COLORS["panel"])
        self.style.configure("Horizontal.TScrollbar", background=COLORS["field"], troughcolor=COLORS["panel"], bordercolor=COLORS["panel"])

    def _build_ui(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.sidebar = ttk.Frame(self, style="Sidebar.TFrame", padding=(18, 20))
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.sidebar.grid_propagate(False)
        self.sidebar.configure(width=252)
        self.sidebar.rowconfigure(8, weight=1)

        ttk.Label(self.sidebar, text="Video Agent", style="Sidebar.TLabel", font=(FONT_FAMILY, 18, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(self.sidebar, text="原生桌面工作台", style="SidebarMuted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 22))
        self.page_buttons["workbench"] = ttk.Button(
            self.sidebar,
            text="分析工作台",
            style="Nav.TButton",
            command=lambda: self.show_page("workbench"),
        )
        self.page_buttons["settings"] = ttk.Button(
            self.sidebar,
            text="设置与密钥",
            style="Nav.TButton",
            command=lambda: self.show_page("settings"),
        )
        self.page_buttons["workbench"].grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self.page_buttons["settings"].grid(row=3, column=0, sticky="ew")

        status_card = ttk.Frame(self.sidebar, style="Sidebar.TFrame")
        status_card.grid(row=9, column=0, sticky="ew")
        ttk.Label(status_card, text="状态", style="SidebarMuted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(status_card, textvariable=self.status, style="Sidebar.TLabel", wraplength=210, justify="left").grid(row=1, column=0, sticky="w", pady=(6, 0))

        self.content = ttk.Frame(self, style="App.TFrame", padding=(22, 20))
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)

        self.workbench = ttk.Frame(self.content, style="App.TFrame")
        self.settings_page = ttk.Frame(self.content, style="App.TFrame")
        for page in (self.workbench, self.settings_page):
            page.grid(row=0, column=0, sticky="nsew")

        self._build_workbench()
        self._build_settings()

    def show_page(self, page):
        self.workbench.grid_remove()
        self.settings_page.grid_remove()
        target = self.workbench if page == "workbench" else self.settings_page
        target.grid(row=0, column=0, sticky="nsew")
        for key, button in self.page_buttons.items():
            button.configure(style="ActiveNav.TButton" if key == page else "Nav.TButton")

    def _build_workbench(self):
        self.workbench.columnconfigure(1, weight=1)
        self.workbench.rowconfigure(1, weight=1)

        ttk.Label(self.workbench, text="逐镜拉片工作台", style="PageTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            self.workbench,
            text="本地路径、GitHub 临时 URL 或公网 URL 都可以在这里发起分析。",
            style="Muted.TLabel",
        ).grid(row=0, column=1, sticky="e", padx=(20, 0))

        control = ttk.Frame(self.workbench, style="Panel.TFrame", padding=18)
        control.grid(row=1, column=0, sticky="nsw", pady=(18, 0), padx=(0, 18))
        control.grid_propagate(False)
        control.configure(width=388)
        control.columnconfigure(0, weight=1)

        ttk.Label(control, text="任务输入", style="Title.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 14))

        self.title_var = tk.StringVar(value="逐镜拉片报告")
        self.analysis_mode = tk.StringVar(value="全模态（画面 + 声音）")
        self.fps = tk.StringVar(value="1")
        self.upload_mode = tk.StringVar(value="local")

        self._field_label(control, "报告标题", 1)
        ttk.Entry(control, textvariable=self.title_var).grid(row=2, column=0, sticky="ew", pady=(0, 12))

        model_row = ttk.Frame(control, style="Panel.TFrame")
        model_row.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        model_row.columnconfigure(0, weight=1)
        model_row.columnconfigure(1, weight=1)
        self._field_label(model_row, "分析模式", 0, column=0)
        self._field_label(model_row, "抽帧 fps", 0, column=1, padx=(10, 0))
        ttk.Combobox(
            model_row,
            textvariable=self.analysis_mode,
            values=list(ANALYSIS_MODE_OPTIONS.keys()),
            state="readonly",
        ).grid(row=1, column=0, sticky="ew", padx=(0, 10))
        ttk.Combobox(model_row, textvariable=self.fps, values=["0.2", "0.5", "1", "2"], state="readonly").grid(row=1, column=1, sticky="ew")

        self._field_label(control, "上传方式", 4)
        ttk.Combobox(control, textvariable=self.upload_mode, values=["local", "github", "url"], state="readonly").grid(row=5, column=0, sticky="ew", pady=(0, 12))

        self._field_label(control, "视频公网 URL", 6)
        ttk.Entry(control, textvariable=self.video_url).grid(row=7, column=0, sticky="ew", pady=(0, 10))

        file_row = ttk.Frame(control, style="Panel.TFrame")
        file_row.grid(row=8, column=0, sticky="ew", pady=(0, 8))
        file_row.columnconfigure(0, weight=1)
        ttk.Button(file_row, text="选择视频", style="Ghost.TButton", command=self.choose_file).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(file_row, text="上传到 GitHub", style="Ghost.TButton", command=self.start_github_upload).grid(row=0, column=1, sticky="ew")
        ttk.Label(control, textvariable=self.local_file, style="PanelMuted.TLabel", wraplength=340).grid(row=9, column=0, sticky="w", pady=(0, 14))

        self._field_label(control, "字幕 / 音轨转写", 10)
        self.subtitle_text = self._text_box(control, height=5)
        self.subtitle_text.grid(row=11, column=0, sticky="ew", pady=(0, 12))

        self._field_label(control, "补充分析要求", 12)
        self.custom_prompt = self._text_box(control, height=5)
        self.custom_prompt.grid(row=13, column=0, sticky="ew", pady=(0, 16))

        ttk.Button(control, text="开始分析", style="Accent.TButton", command=self.start_analysis).grid(row=14, column=0, sticky="ew")
        export_row = ttk.Frame(control, style="Panel.TFrame")
        export_row.grid(row=15, column=0, sticky="ew", pady=(10, 0))
        export_row.columnconfigure(0, weight=1)
        export_row.columnconfigure(1, weight=1)
        ttk.Button(export_row, text="导出 Markdown", style="Ghost.TButton", command=self.export_markdown_file).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(export_row, text="导出 CSV", style="Ghost.TButton", command=self.export_csv_file).grid(row=0, column=1, sticky="ew")

        main = ttk.Frame(self.workbench, style="App.TFrame")
        main.grid(row=1, column=1, sticky="nsew", pady=(18, 0))
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        cover = ttk.Frame(main, style="Card.TFrame", padding=(18, 14))
        cover.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        cover.columnconfigure(0, weight=1)
        ttk.Label(cover, textvariable=self.report_title_var, style="Card.TLabel", font=(FONT_FAMILY, 16, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(cover, textvariable=self.report_meta_var, style="Card.TLabel", foreground=COLORS["muted"]).grid(row=1, column=0, sticky="w", pady=(6, 0))

        table_card = ttk.Frame(main, style="Panel.TFrame", padding=(1, 1))
        table_card.grid(row=1, column=0, sticky="nsew")
        table_card.columnconfigure(0, weight=1)
        table_card.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            table_card,
            style="Report.Treeview",
            columns=("shot", "timecode", "size", "camera", "visual", "audio", "analysis"),
            show="headings",
            selectmode="browse",
        )
        columns = {
            "shot": ("镜号", 88),
            "timecode": ("时间码", 118),
            "size": ("景别", 86),
            "camera": ("镜头运动", 116),
            "visual": ("画面内容 / 人物动作", 360),
            "audio": ("声音 / 音乐", 220),
            "analysis": ("分析注释", 360),
        }
        for key, (label, width) in columns.items():
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=width, anchor="w", stretch=key in {"visual", "analysis"})
        y_scroll = ttk.Scrollbar(table_card, orient="vertical", command=self.tree.yview)
        x_scroll = ttk.Scrollbar(table_card, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.tree.tag_configure("even", background=COLORS["panel"])
        self.tree.tag_configure("odd", background="#0d1525")
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        detail_card = ttk.Frame(main, style="Card.TFrame", padding=(16, 12))
        detail_card.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        detail_card.columnconfigure(0, weight=1)
        ttk.Label(detail_card, text="选中镜头详情", style="SmallTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.detail_text = self._text_box(detail_card, height=7, background=COLORS["panel_alt"])
        self.detail_text.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self._set_text(self.detail_text, "分析完成后，点击任意镜头查看完整字段。")

    def _build_settings(self):
        self.settings_page.columnconfigure(0, weight=1)
        self.settings_page.rowconfigure(1, weight=1)
        ttk.Label(self.settings_page, text="设置与密钥", style="PageTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            self.settings_page,
            text="密钥会保存到本地 .env；留空的密钥字段会保留原值。",
            style="Muted.TLabel",
        ).grid(row=0, column=0, sticky="e")

        card = ttk.Frame(self.settings_page, style="Panel.TFrame", padding=22)
        card.grid(row=1, column=0, sticky="nsew", pady=(18, 0))
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)

        rows = [
            ("dashscope_api_key", "DASHSCOPE_API_KEY", True),
            ("workspace_id", "Workspace ID", False),
            ("region", "Region", False),
            ("dashscope_base_url", "Base URL", False),
            ("vision_model", "视觉模型", False),
            ("omni_model", "全模态模型", False),
            ("github_token", "GitHub Token", True),
            ("github_owner", "GitHub Owner", False),
            ("github_repo", "GitHub Repo", False),
            ("github_release_tag", "Release Tag", False),
            ("github_release_name", "Release Name", False),
            ("github_asset_prefix", "Asset Prefix", False),
        ]
        for index, (key, label, secret) in enumerate(rows):
            row = index // 2
            col = index % 2
            padx = (0, 14) if col == 0 else (14, 0)
            ttk.Label(card, text=label, style="PanelMuted.TLabel").grid(row=row * 2, column=col, sticky="w", pady=(0, 6), padx=padx)
            var = tk.StringVar()
            entry = ttk.Entry(card, textvariable=var, show="*" if secret else "")
            entry.grid(row=row * 2 + 1, column=col, sticky="ew", pady=(0, 14), padx=padx)
            self.fields[key] = var

        self.secret_note = tk.StringVar(value="")
        ttk.Label(card, textvariable=self.secret_note, style="PanelMuted.TLabel").grid(row=13, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Button(card, text="保存配置", style="Accent.TButton", command=self.save_settings).grid(row=14, column=1, sticky="e", pady=(18, 0))

    def _field_label(self, parent, text, row, column=0, padx=(0, 0)):
        ttk.Label(parent, text=text, style="PanelMuted.TLabel").grid(row=row, column=column, sticky="w", pady=(0, 6), padx=padx)

    def _text_box(self, parent, height=4, background=None):
        box = tk.Text(
            parent,
            height=height,
            wrap="word",
            relief="flat",
            bd=0,
            padx=10,
            pady=8,
            bg=background or COLORS["field"],
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            selectbackground=COLORS["accent_soft"],
            selectforeground=COLORS["text"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            highlightcolor=COLORS["accent"],
            font=(FONT_FAMILY, 10),
        )
        return box

    def _set_text(self, widget, value):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def load_settings(self):
        config = get_config()
        for key, var in self.fields.items():
            if key in ("dashscope_api_key", "github_token"):
                var.set("")
            else:
                var.set(str(config.get(key, "")))
        self.secret_note.set(
            f"当前密钥：API Key {mask_secret(config.get('dashscope_api_key'))}    GitHub {mask_secret(config.get('github_token'))}"
        )

    def save_settings(self):
        updates = {key: var.get().strip() for key, var in self.fields.items()}
        save_config(updates)
        self.load_settings()
        self.set_status("配置已保存")
        messagebox.showinfo("设置", "配置已保存。空白密钥字段会保留原值。")

    def choose_file(self):
        path = filedialog.askopenfilename(
            title="选择视频",
            filetypes=[("Video files", "*.mp4 *.mov *.m4v *.webm *.avi *.mkv"), ("All files", "*.*")],
        )
        if path:
            self.local_file.set(path)
            self.set_status(f"已选择视频：{Path(path).name}")

    def start_github_upload(self):
        if not self.local_file.get():
            self.choose_file()
        local_path = self.local_file.get()
        if not local_path:
            return
        self.run_background(lambda: self._github_upload_task(local_path))

    def _github_upload_task(self, local_path):
        self.set_status("正在上传到 GitHub Releases...")
        url = upload_to_github_release(local_path)
        self.set_public_url(url)
        self.set_status("GitHub 上传完成，URL 已填入")

    def start_analysis(self):
        inputs = {
            "mode": self.upload_mode.get(),
            "video_url": self.video_url.get().strip(),
            "local_path": self.local_file.get(),
            "title": self.title_var.get().strip() or "逐镜拉片报告",
            "analysis_mode": self.analysis_mode_value(),
            "fps": self.fps.get(),
            "subtitle_text": self.subtitle_text.get("1.0", "end").strip(),
            "custom_prompt": self.custom_prompt.get("1.0", "end").strip(),
        }
        self.run_background(lambda: self._analysis_task(inputs))

    def analysis_mode_value(self):
        return ANALYSIS_MODE_OPTIONS.get(self.analysis_mode.get(), "omni")

    def _analysis_task(self, inputs):
        mode = inputs["mode"]
        video_url = inputs["video_url"]
        local_path = inputs["local_path"] if mode == "local" else ""
        if mode in ("local", "github") and not inputs["local_path"]:
            raise RuntimeError("请先选择本地视频文件。")
        if mode == "url" and not video_url:
            raise RuntimeError("请先填写视频公网 URL。")
        if mode == "github":
            self.set_status("正在上传到 GitHub Releases...")
            url = upload_to_github_release(inputs["local_path"])
            self.set_public_url(url)
            video_url = url
            local_path = ""
        self.set_status("正在分析视频...")
        result = analyze_video(
            title=inputs["title"],
            video_url=video_url,
            local_path=local_path,
            analysis_mode=inputs["analysis_mode"],
            fps=inputs["fps"],
            subtitle_text=inputs["subtitle_text"],
            custom_prompt=inputs["custom_prompt"],
        )
        self.after(0, lambda: self.apply_report(result["report"]))
        shot_count = len(result["report"].get("shots", []))
        self.set_status(f"分析完成：{shot_count} 个镜头")

    def set_public_url(self, url):
        def apply():
            self.video_url.set(url)
            self.upload_mode.set("url")

        self.after(0, apply)

    def apply_report(self, report):
        self.report = report
        meta = report.get("meta", {})
        shots = report.get("shots", [])
        self.report_title_var.set(meta.get("title") or "逐镜拉片报告")
        self.report_meta_var.set(
            f"{meta.get('duration') or '片长待识别'} · {meta.get('sceneCount') or 0} 场景 · "
            f"{meta.get('shotCount') or len(shots)} 镜 · {meta.get('basis') or '视觉理解分析'}"
        )
        self.render_report()

    def render_report(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.tree_item_map = {}
        for index, shot in enumerate(self.report.get("shots", [])):
            item = self.tree.insert(
                "",
                "end",
                values=(
                    shot.get("shot", ""),
                    shot.get("timecode", ""),
                    shot.get("shotSize", ""),
                    shot.get("camera", ""),
                    self.compact(shot.get("visual", "")),
                    self.compact(shot.get("audio", "")),
                    self.compact(shot.get("analysis", "")),
                ),
                tags=("odd" if index % 2 else "even",),
            )
            self.tree_item_map[item] = shot
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])
            self.update_detail(self.tree_item_map[children[0]])
        else:
            self._set_text(self.detail_text, "没有可展示的镜头。")

    def on_tree_select(self, _event):
        selection = self.tree.selection()
        if not selection:
            return
        shot = self.tree_item_map.get(selection[0])
        if shot:
            self.update_detail(shot)

    def update_detail(self, shot):
        lines = [
            f"镜号：{shot.get('shot', '')}",
            f"场景：{shot.get('scene', '')}",
            f"时间码：{shot.get('timecode', '')}",
            f"景别：{shot.get('shotSize', '')}",
            f"镜头运动：{shot.get('camera', '')}",
            "",
            f"画面内容 / 人物动作：\n{shot.get('visual', '')}",
            "",
            f"声音 / 音乐：\n{shot.get('audio', '')}",
            "",
            f"分析注释：\n{shot.get('analysis', '')}",
        ]
        self._set_text(self.detail_text, "\n".join(lines))

    def compact(self, value, limit=120):
        text = " ".join(str(value or "").split())
        if len(text) <= limit:
            return text
        return text[: limit - 1] + "…"

    def export_markdown_file(self):
        if not self.report:
            messagebox.showwarning("导出", "还没有报告。")
            return
        path = filedialog.asksaveasfilename(defaultextension=".md", filetypes=[("Markdown", "*.md")])
        if path:
            export_markdown(self.report, path)
            self.set_status(f"已导出 Markdown：{path}")

    def export_csv_file(self):
        if not self.report:
            messagebox.showwarning("导出", "还没有报告。")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if path:
            export_csv(self.report, path)
            self.set_status(f"已导出 CSV：{path}")

    def run_background(self, target):
        def runner():
            try:
                target()
            except Exception as exc:
                message = str(exc)
                self.set_status(f"错误：{message}")
                self.after(0, lambda: messagebox.showerror("错误", message))

        threading.Thread(target=runner, daemon=True).start()

    def set_status(self, text):
        self.after(0, lambda: self.status.set(text))


if __name__ == "__main__":
    enable_high_dpi_awareness()
    app = VideoAgentApp()
    app.mainloop()
