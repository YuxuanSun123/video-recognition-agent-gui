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


FONT_UI = "Microsoft YaHei UI"
FONT_DISPLAY = "Arial Black"
FONT_MONO = "Consolas"

COLORS = {
    "paper_bg": "#d4d0c1",
    "paper": "#f4efe3",
    "paper_2": "#faf6ea",
    "ink": "#0b0b09",
    "ink_2": "#1d1d1a",
    "muted": "#5b5a52",
    "muted_2": "#7a786c",
    "line": "#0b0b09",
    "acid": "#ccff00",
    "acid_dim": "#a9d800",
    "white": "#fffdf5",
    "danger": "#d14b2f",
}

ANALYSIS_MODE_OPTIONS = {
    "视频理解主力（qwen3.7-plus）": "vision",
    "声音/对白专精（qwen3.5-omni-plus）": "omni",
}

UPLOAD_MODE_OPTIONS = {
    "本地路径 · 100MB": "local",
    "GitHub Release URL": "github",
    "公网 URL": "url",
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
        self.title("Shot Reader - 视频识别 Agent")
        self.geometry("1480x920")
        self.minsize(1220, 780)
        self.configure(bg=COLORS["paper_bg"])
        self._sync_tk_scaling()

        self.report = None
        self.tree_item_map = {}
        self.fields = {}
        self.page_buttons = {}
        self.local_file = tk.StringVar()
        self.video_url = tk.StringVar()
        self.status = tk.StringVar(value="DASHSCOPE 已连接")
        self.report_title_var = tk.StringVar(value="样例短片 · 逐镜拉片报告")
        self.report_meta_var = tk.StringVar(value="基于逐秒截帧的视听语言分析，导出 Markdown 与 CSV。")
        self.scene_count_var = tk.StringVar(value="00")
        self.shot_count_var = tk.StringVar(value="00")
        self.task_mode_var = tk.StringVar(value="READY")

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
        self.option_add("*Font", (FONT_UI, 10))
        self.style = ttk.Style(self)
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")

        self.style.configure(".", font=(FONT_UI, 10))
        self.style.configure("Paper.TFrame", background=COLORS["paper"])
        self.style.configure("PaperBg.TFrame", background=COLORS["paper_bg"])
        self.style.configure("Ink.TFrame", background=COLORS["ink"])
        self.style.configure("Rail.TFrame", background=COLORS["paper_2"])
        self.style.configure("TLabel", background=COLORS["paper"], foreground=COLORS["ink"])
        self.style.configure("Paper.TLabel", background=COLORS["paper"], foreground=COLORS["ink"])
        self.style.configure("Ink.TLabel", background=COLORS["ink"], foreground=COLORS["white"])
        self.style.configure("Muted.TLabel", background=COLORS["paper"], foreground=COLORS["muted"])
        self.style.configure("Mono.TLabel", background=COLORS["paper"], foreground=COLORS["ink"], font=(FONT_MONO, 9, "bold"))
        self.style.configure("Acid.TLabel", background=COLORS["ink"], foreground=COLORS["acid"], font=(FONT_MONO, 8, "bold"))
        self.style.configure("Title.TLabel", background=COLORS["paper"], foreground=COLORS["ink"], font=(FONT_UI, 20, "bold"))
        self.style.configure("HeroTitle.TLabel", background=COLORS["ink"], foreground=COLORS["white"], font=(FONT_UI, 20, "bold"))
        self.style.configure("HeroMuted.TLabel", background=COLORS["ink"], foreground="#bfc4bd", font=(FONT_UI, 10))
        self.style.configure("Metric.TLabel", background=COLORS["ink"], foreground=COLORS["white"], font=(FONT_DISPLAY, 18))
        self.style.configure("MetricAccent.TLabel", background=COLORS["ink"], foreground=COLORS["acid"], font=(FONT_DISPLAY, 18))
        self.style.configure("FieldLabel.TLabel", background=COLORS["paper"], foreground=COLORS["ink"], font=(FONT_MONO, 8, "bold"))

        field_opts = {
            "fieldbackground": COLORS["white"],
            "foreground": COLORS["ink"],
            "insertcolor": COLORS["ink"],
            "bordercolor": COLORS["line"],
            "lightcolor": COLORS["line"],
            "darkcolor": COLORS["line"],
            "padding": 8,
        }
        self.style.configure("TEntry", **field_opts)
        self.style.configure(
            "TCombobox",
            fieldbackground=COLORS["white"],
            background=COLORS["white"],
            foreground=COLORS["ink"],
            arrowcolor=COLORS["ink"],
            bordercolor=COLORS["line"],
            lightcolor=COLORS["line"],
            darkcolor=COLORS["line"],
            padding=8,
        )
        self.style.map(
            "TCombobox",
            fieldbackground=[("readonly", COLORS["white"])],
            foreground=[("readonly", COLORS["ink"])],
            selectbackground=[("readonly", COLORS["white"])],
            selectforeground=[("readonly", COLORS["ink"])],
        )
        self.style.configure(
            "Overprint.Treeview",
            background=COLORS["paper_2"],
            fieldbackground=COLORS["paper_2"],
            foreground=COLORS["ink"],
            bordercolor=COLORS["line"],
            rowheight=34,
            font=(FONT_UI, 10),
        )
        self.style.configure(
            "Overprint.Treeview.Heading",
            background=COLORS["ink"],
            foreground=COLORS["acid"],
            relief="flat",
            font=(FONT_MONO, 8, "bold"),
            padding=8,
        )
        self.style.map(
            "Overprint.Treeview",
            background=[("selected", COLORS["acid"])],
            foreground=[("selected", COLORS["ink"])],
        )
        self.style.configure("Vertical.TScrollbar", background=COLORS["paper"], troughcolor=COLORS["paper_2"], bordercolor=COLORS["line"])
        self.style.configure("Horizontal.TScrollbar", background=COLORS["paper"], troughcolor=COLORS["paper_2"], bordercolor=COLORS["line"])

    def _build_ui(self):
        self.columnconfigure(2, weight=1)
        self.rowconfigure(0, weight=1)

        self.sidebar = tk.Frame(self, bg=COLORS["ink"], width=230)
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.sidebar.grid_propagate(False)
        self.sidebar.rowconfigure(9, weight=1)
        self._build_sidebar()

        self.rail = tk.Frame(self, bg=COLORS["paper_2"], width=44, highlightthickness=2, highlightbackground=COLORS["ink"])
        self.rail.grid(row=0, column=1, sticky="ns", padx=(0, 0), pady=26)
        self.rail.grid_propagate(False)
        self._build_rail()

        shell = tk.Frame(self, bg=COLORS["ink"], padx=0, pady=0)
        shell.grid(row=0, column=2, sticky="nsew", padx=(0, 28), pady=(26, 34))
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(0, weight=1)

        self.main = tk.Frame(shell, bg=COLORS["paper"], highlightthickness=2, highlightbackground=COLORS["ink"])
        self.main.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 8))
        self.main.columnconfigure(0, weight=1)
        self.main.rowconfigure(2, weight=1)

        self._build_header()

        self.page_host = tk.Frame(self.main, bg=COLORS["paper"])
        self.page_host.grid(row=2, column=0, sticky="nsew", padx=24, pady=(14, 22))
        self.page_host.columnconfigure(0, weight=1)
        self.page_host.rowconfigure(0, weight=1)

        self.workbench = tk.Frame(self.page_host, bg=COLORS["paper"])
        self.settings_page = tk.Frame(self.page_host, bg=COLORS["paper"])
        for page in (self.workbench, self.settings_page):
            page.grid(row=0, column=0, sticky="nsew")

        self._build_workbench()
        self._build_settings()

    def _build_sidebar(self):
        top = tk.Frame(self.sidebar, bg=COLORS["ink"])
        top.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 26))
        tk.Label(top, text="逐镜\n拉片", bg=COLORS["ink"], fg=COLORS["white"], font=(FONT_UI, 18, "bold"), justify="left").grid(row=0, column=0, sticky="w")
        tk.Label(top, text="SHOT READER", bg=COLORS["ink"], fg=COLORS["acid"], font=(FONT_MONO, 8, "bold")).grid(row=1, column=0, sticky="w", pady=(6, 0))

        self.page_buttons["workbench"] = self._nav_button("分析任务", lambda: self.show_page("workbench"))
        self.page_buttons["settings"] = self._nav_button("设置与密钥", lambda: self.show_page("settings"))
        self.page_buttons["workbench"].grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))
        self._nav_button("报告库", None).grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 10))
        self._nav_button("提示词", None).grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 10))
        self.page_buttons["settings"].grid(row=4, column=0, sticky="ew", padx=18, pady=(0, 10))

        status = tk.Frame(self.sidebar, bg=COLORS["ink"])
        status.grid(row=10, column=0, sticky="ew", padx=18, pady=(0, 22))
        tk.Frame(status, bg=COLORS["muted"], height=1).grid(row=0, column=0, sticky="ew", pady=(0, 16))
        status.columnconfigure(0, weight=1)
        row = tk.Frame(status, bg=COLORS["ink"])
        row.grid(row=1, column=0, sticky="w")
        tk.Label(row, text="■", bg=COLORS["ink"], fg=COLORS["acid"], font=(FONT_MONO, 10, "bold")).pack(side="left")
        tk.Label(row, textvariable=self.status, bg=COLORS["ink"], fg=COLORS["white"], font=(FONT_UI, 10, "bold")).pack(side="left", padx=(6, 0))
        cfg = get_config()
        tk.Label(status, text=f"{cfg.get('vision_model', 'qwen3.7-plus').upper()}\n全栈本地连接\n127.0.0.1:5177", bg=COLORS["ink"], fg="#c4c8c0", font=(FONT_MONO, 8), justify="left").grid(row=2, column=0, sticky="w", pady=(10, 0))

    def _nav_button(self, text, command):
        return tk.Button(
            self.sidebar,
            text=text,
            command=command or (lambda: None),
            bg=COLORS["ink"],
            fg="#c8ccd0",
            activebackground=COLORS["ink"],
            activeforeground=COLORS["acid"],
            relief="flat",
            bd=0,
            anchor="w",
            padx=12,
            pady=10,
            highlightthickness=1,
            highlightbackground=COLORS["ink"],
            font=(FONT_UI, 10, "bold" if command else "normal"),
        )

    def _build_rail(self):
        self.rail.rowconfigure(4, weight=1)
        tk.Label(self.rail, text="●", bg=COLORS["paper_2"], fg="#394047", font=(FONT_MONO, 12, "bold")).grid(row=0, column=0, pady=(14, 8))
        tk.Label(self.rail, text=self.vertical_text("DASHSCOPE 已连接"), bg=COLORS["paper_2"], fg=COLORS["muted"], font=(FONT_MONO, 8, "bold"), justify="center").grid(row=1, column=0, pady=(0, 18))
        tk.Label(self.rail, text=self.vertical_text("MODEL QWEN3.7 PLUS"), bg=COLORS["paper_2"], fg=COLORS["acid_dim"], font=(FONT_MONO, 8, "bold"), justify="center").grid(row=2, column=0, pady=(0, 18))
        tk.Label(self.rail, text=self.vertical_text("FPS 1.0"), bg=COLORS["paper_2"], fg=COLORS["acid_dim"], font=(FONT_MONO, 8, "bold"), justify="center").grid(row=3, column=0, pady=(0, 18))
        tk.Label(self.rail, text=self.vertical_text("上传 本地路径"), bg=COLORS["paper_2"], fg=COLORS["muted"], font=(FONT_MONO, 8, "bold"), justify="center").grid(row=5, column=0, pady=(18, 14))

    def _build_header(self):
        header = tk.Frame(self.main, bg=COLORS["paper"])
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(24, 0))
        header.columnconfigure(0, weight=1)
        tk.Label(header, text="NO.06 / SHOT-BY-SHOT DOSSIER", bg=COLORS["paper"], fg=COLORS["ink"], font=(FONT_MONO, 8, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(header, text="视频识别 AGENT · 逐镜拉片", bg=COLORS["paper"], fg=COLORS["ink"], font=(FONT_UI, 18, "bold")).grid(row=1, column=0, sticky="w", pady=(3, 0))

        actions = tk.Frame(header, bg=COLORS["paper"])
        actions.grid(row=0, column=1, rowspan=2, sticky="e")
        self._header_button(actions, "导出 MD", self.export_markdown_file).pack(side="left", padx=(0, 8))
        self._header_button(actions, "导出 CSV", self.export_csv_file).pack(side="left", padx=(0, 8))
        self._header_button(actions, "开始分析 →", self.start_analysis, primary=True).pack(side="left")

        tk.Frame(self.main, bg=COLORS["ink"], height=4).grid(row=1, column=0, sticky="ew", padx=24, pady=(12, 0))

    def _header_button(self, parent, text, command, primary=False):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=COLORS["ink"] if primary else COLORS["paper"],
            fg=COLORS["white"] if primary else COLORS["ink"],
            activebackground=COLORS["acid"] if primary else COLORS["white"],
            activeforeground=COLORS["ink"],
            relief="flat",
            bd=0,
            highlightthickness=2,
            highlightbackground=COLORS["ink"],
            padx=18,
            pady=10,
            font=(FONT_UI, 9, "bold"),
        )

    def show_page(self, page):
        self.workbench.grid_remove()
        self.settings_page.grid_remove()
        target = self.workbench if page == "workbench" else self.settings_page
        target.grid(row=0, column=0, sticky="nsew")
        for key, button in self.page_buttons.items():
            active = key == page
            button.configure(
                fg=COLORS["acid"] if active else "#c8ccd0",
                highlightbackground=COLORS["acid"] if active else COLORS["ink"],
                font=(FONT_UI, 10, "bold" if active else "normal"),
            )

    def _build_workbench(self):
        self.workbench.columnconfigure(0, weight=1)
        self.workbench.rowconfigure(1, weight=1)

        setup = self._section(self.workbench, "1", "输入设置 · SETUP", "配置视频与分析参数")
        setup.grid(row=0, column=0, sticky="ew")
        setup.body.columnconfigure(0, weight=1)

        hero = tk.Frame(setup.body, bg=COLORS["ink"])
        hero.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 14))
        hero.columnconfigure(0, weight=1)
        hero.columnconfigure(1, weight=1)
        left = tk.Frame(hero, bg=COLORS["ink"])
        left.grid(row=0, column=0, sticky="nsew", padx=24, pady=22)
        tk.Label(left, text="ANALYSIS BRIEF", bg=COLORS["ink"], fg=COLORS["acid"], font=(FONT_MONO, 8, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(left, textvariable=self.report_title_var, bg=COLORS["ink"], fg=COLORS["white"], font=(FONT_UI, 20, "bold")).grid(row=1, column=0, sticky="w", pady=(10, 8))
        tk.Label(left, textvariable=self.report_meta_var, bg=COLORS["ink"], fg="#c5c8bf", font=(FONT_UI, 10), wraplength=520, justify="left").grid(row=2, column=0, sticky="w")
        metrics = tk.Frame(left, bg=COLORS["ink"])
        metrics.grid(row=3, column=0, sticky="w", pady=(18, 0))
        self._metric(metrics, self.scene_count_var, "场景", accent=False).pack(side="left", padx=(0, 22))
        self._metric(metrics, self.shot_count_var, "镜头", accent=True).pack(side="left", padx=(0, 22))
        self._metric(metrics, self.task_mode_var, "分析任务", accent=False).pack(side="left")

        preview_wrap = tk.Frame(hero, bg=COLORS["acid"], padx=3, pady=3)
        preview_wrap.grid(row=0, column=1, sticky="nsew", padx=(14, 22), pady=20)
        preview = tk.Frame(preview_wrap, bg="#171c24")
        preview.grid(row=0, column=0, sticky="nsew")
        preview_wrap.columnconfigure(0, weight=1)
        preview_wrap.rowconfigure(0, weight=1)
        tk.Label(preview, text="▶  等待视频 URL", bg="#171c24", fg="#cdd2d7", font=(FONT_MONO, 9, "bold")).place(relx=0.5, rely=0.5, anchor="center")

        form = tk.Frame(setup.body, bg=COLORS["paper"], highlightthickness=2, highlightbackground=COLORS["ink"])
        form.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 16))
        for col in range(6):
            form.columnconfigure(col, weight=1)

        self.title_var = tk.StringVar(value="逐镜拉片报告")
        self.analysis_mode = tk.StringVar(value="视频理解主力（qwen3.7-plus）")
        self.fps = tk.StringVar(value="1")
        self.upload_mode = tk.StringVar(value="本地路径 · 100MB")

        self._field(form, "视频公网 URL", 0, 0, colspan=3, widget=ttk.Entry(form, textvariable=self.video_url))
        self._field(form, "报告标题", 0, 3, colspan=2, widget=ttk.Entry(form, textvariable=self.title_var))
        self._field(form, "抽帧 FPS", 0, 5, widget=ttk.Combobox(form, textvariable=self.fps, values=["0.2", "0.5", "1", "2"], state="readonly"))
        self._field(form, "分析模型", 2, 0, colspan=2, widget=ttk.Combobox(form, textvariable=self.analysis_mode, values=list(ANALYSIS_MODE_OPTIONS.keys()), state="readonly"))
        self._field(form, "上传方式", 2, 2, colspan=2, widget=ttk.Combobox(form, textvariable=self.upload_mode, values=list(UPLOAD_MODE_OPTIONS.keys()), state="readonly"))

        file_box = tk.Frame(form, bg=COLORS["white"], highlightthickness=1, highlightbackground=COLORS["ink"])
        tk.Button(file_box, text="选择文件", command=self.choose_file, bg=COLORS["white"], fg=COLORS["ink"], relief="flat", bd=0, highlightthickness=1, highlightbackground=COLORS["ink"], font=(FONT_UI, 9, "bold")).pack(side="left", padx=10, pady=8)
        tk.Button(file_box, text="上传 GitHub", command=self.start_github_upload, bg=COLORS["paper"], fg=COLORS["ink"], relief="flat", bd=0, highlightthickness=1, highlightbackground=COLORS["ink"], font=(FONT_UI, 9, "bold")).pack(side="left", padx=(0, 10), pady=8)
        tk.Label(file_box, textvariable=self.local_file, bg=COLORS["white"], fg=COLORS["muted"], font=(FONT_UI, 9), anchor="w").pack(side="left", fill="x", expand=True, padx=(0, 10))
        self._field(form, "本地文件", 2, 4, colspan=2, widget=file_box)

        self.subtitle_text = self._text_box(form, height=4)
        self.custom_prompt = self._text_box(form, height=4)
        self._field(form, "字幕 / 音轨转写", 4, 0, colspan=3, widget=self.subtitle_text)
        self._field(form, "补充分析要求", 4, 3, colspan=3, widget=self.custom_prompt)

        result = self._section(self.workbench, "2", "逐镜结果 · RESULT", "点击单行查看完整字段")
        result.grid(row=1, column=0, sticky="nsew", pady=(14, 0))
        result.body.columnconfigure(0, weight=1)
        result.body.rowconfigure(0, weight=1)
        self._build_result_area(result.body)

    def _build_result_area(self, parent):
        table_wrap = tk.Frame(parent, bg=COLORS["ink"], padx=2, pady=2)
        table_wrap.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        table_wrap.columnconfigure(0, weight=1)
        table_wrap.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            table_wrap,
            style="Overprint.Treeview",
            columns=("shot", "timecode", "size", "camera", "visual", "audio", "analysis"),
            show="headings",
            selectmode="browse",
            height=7,
        )
        columns = {
            "shot": ("镜号", 78),
            "timecode": ("时间码", 112),
            "size": ("景别", 80),
            "camera": ("镜头运动", 108),
            "visual": ("画面内容 / 人物动作", 340),
            "audio": ("声音 / 音乐", 200),
            "analysis": ("分析注释", 320),
        }
        for key, (label, width) in columns.items():
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=width, anchor="w", stretch=key in {"visual", "analysis"})
        y_scroll = ttk.Scrollbar(table_wrap, orient="vertical", command=self.tree.yview)
        x_scroll = ttk.Scrollbar(table_wrap, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.tree.tag_configure("even", background=COLORS["paper_2"])
        self.tree.tag_configure("odd", background="#eee8d9")
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        self.detail_text = self._text_box(parent, height=8, bg=COLORS["white"])
        self.detail_text.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 16))
        self._set_text(self.detail_text, "分析完成后，点击任意镜头查看完整字段。")

    def _build_settings(self):
        self.settings_page.columnconfigure(0, weight=1)
        section = self._section(self.settings_page, "3", "设置与密钥 · KEYS", "留空密钥字段会保留原值")
        section.grid(row=0, column=0, sticky="nsew")
        section.body.columnconfigure(0, weight=1)
        section.body.rowconfigure(0, weight=1)

        form = tk.Frame(section.body, bg=COLORS["paper"], highlightthickness=2, highlightbackground=COLORS["ink"])
        form.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)
        rows = [
            ("dashscope_api_key", "DASHSCOPE_API_KEY", True),
            ("workspace_id", "Workspace ID", False),
            ("region", "Region", False),
            ("dashscope_base_url", "Base URL", False),
            ("vision_model", "视频理解模型", False),
            ("omni_model", "声音专精模型", False),
            ("github_token", "GitHub Token", True),
            ("github_owner", "GitHub Owner", False),
            ("github_repo", "GitHub Repo", False),
            ("github_release_tag", "Release Tag", False),
            ("github_release_name", "Release Name", False),
            ("github_asset_prefix", "Asset Prefix", False),
        ]
        for index, (key, label, secret) in enumerate(rows):
            row = (index // 2) * 2
            col = index % 2
            padx = (14, 8) if col == 0 else (8, 14)
            tk.Label(form, text=label, bg=COLORS["paper"], fg=COLORS["ink"], font=(FONT_MONO, 8, "bold")).grid(row=row, column=col, sticky="w", padx=padx, pady=(14, 4))
            var = tk.StringVar()
            entry = ttk.Entry(form, textvariable=var, show="*" if secret else "")
            entry.grid(row=row + 1, column=col, sticky="ew", padx=padx, pady=(0, 4))
            self.fields[key] = var

        self.secret_note = tk.StringVar(value="")
        tk.Label(form, textvariable=self.secret_note, bg=COLORS["paper"], fg=COLORS["muted"], font=(FONT_MONO, 8)).grid(row=12, column=0, columnspan=2, sticky="w", padx=14, pady=(18, 8))
        self._header_button(form, "保存配置", self.save_settings, primary=True).grid(row=13, column=1, sticky="e", padx=14, pady=(8, 18))

    def _section(self, parent, number, title, right_text):
        outer = tk.Frame(parent, bg=COLORS["paper"], highlightthickness=2, highlightbackground=COLORS["ink"])
        header = tk.Frame(outer, bg=COLORS["ink"])
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        tk.Label(header, text=number, bg=COLORS["acid"], fg=COLORS["ink"], font=(FONT_MONO, 9, "bold"), padx=8, pady=3).grid(row=0, column=0, sticky="w", padx=(16, 10), pady=12)
        tk.Label(header, text=title, bg=COLORS["ink"], fg=COLORS["acid"], font=(FONT_MONO, 8, "bold")).grid(row=0, column=1, sticky="w")
        tk.Label(header, text=right_text, bg=COLORS["ink"], fg="#b7bbb4", font=(FONT_UI, 8)).grid(row=0, column=2, sticky="e", padx=16)
        body = tk.Frame(outer, bg=COLORS["paper"])
        body.grid(row=1, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)
        outer.body = body
        return outer

    def _metric(self, parent, value_var, label, accent=False):
        frame = tk.Frame(parent, bg=COLORS["ink"])
        tk.Label(frame, textvariable=value_var, bg=COLORS["ink"], fg=COLORS["acid"] if accent else COLORS["white"], font=(FONT_DISPLAY, 18)).grid(row=0, column=0, sticky="w")
        tk.Label(frame, text=label, bg=COLORS["ink"], fg="#c5c8bf", font=(FONT_MONO, 8, "bold")).grid(row=1, column=0, sticky="w")
        return frame

    def _field(self, parent, label, row, col, widget, colspan=1):
        tk.Label(parent, text=label, bg=COLORS["paper"], fg=COLORS["ink"], font=(FONT_MONO, 8, "bold")).grid(row=row, column=col, columnspan=colspan, sticky="w", padx=14, pady=(14, 4))
        widget.grid(row=row + 1, column=col, columnspan=colspan, sticky="ew", padx=14, pady=(0, 10))

    def _text_box(self, parent, height=4, bg=None):
        return tk.Text(
            parent,
            height=height,
            wrap="word",
            relief="flat",
            bd=0,
            padx=10,
            pady=8,
            bg=bg or COLORS["white"],
            fg=COLORS["ink"],
            insertbackground=COLORS["ink"],
            selectbackground=COLORS["acid"],
            selectforeground=COLORS["ink"],
            highlightthickness=1,
            highlightbackground=COLORS["ink"],
            highlightcolor=COLORS["acid"],
            font=(FONT_UI, 10),
        )

    def _set_text(self, widget, value):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def vertical_text(self, text):
        return "\n".join(text)

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
        self.set_status("正在上传到 GitHub")
        url = upload_to_github_release(local_path)
        self.set_public_url(url)
        self.set_status("GitHub URL 已填入")

    def start_analysis(self):
        inputs = {
            "mode": self.upload_mode_value(),
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
        return ANALYSIS_MODE_OPTIONS.get(self.analysis_mode.get(), "vision")

    def upload_mode_value(self):
        return UPLOAD_MODE_OPTIONS.get(self.upload_mode.get(), "local")

    def _analysis_task(self, inputs):
        mode = inputs["mode"]
        video_url = inputs["video_url"]
        local_path = inputs["local_path"] if mode == "local" else ""
        if mode in ("local", "github") and not inputs["local_path"]:
            raise RuntimeError("请先选择本地视频文件。")
        if mode == "url" and not video_url:
            raise RuntimeError("请先填写视频公网 URL。")
        if mode == "github":
            self.set_status("正在上传到 GitHub")
            url = upload_to_github_release(inputs["local_path"])
            self.set_public_url(url)
            video_url = url
            local_path = ""
        self.set_status("正在分析视频")
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
        self.set_status(f"分析完成：{shot_count} 镜")

    def set_public_url(self, url):
        def apply():
            self.video_url.set(url)
            self.upload_mode.set("公网 URL")

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
        self.scene_count_var.set(f"{int(meta.get('sceneCount') or 0):02d}")
        self.shot_count_var.set(f"{int(meta.get('shotCount') or len(shots)):02d}")
        self.task_mode_var.set("LIVE")
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
            self.set_status("Markdown 已导出")

    def export_csv_file(self):
        if not self.report:
            messagebox.showwarning("导出", "还没有报告。")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if path:
            export_csv(self.report, path)
            self.set_status("CSV 已导出")

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
