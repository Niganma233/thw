"""图源管理器 UI：列表、拖拽排序、启用/禁用、编辑、测试。"""
import threading
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from core import config_store
from services import downloader
from services.sources import SourceManager
from ui import theme
from ui.widgets import make_card


class SourceManagerView:
    def __init__(self, parent, cfg, manager=None, on_changed=None, on_status=None):
        self.parent = parent
        self.cfg = cfg
        # 管理器由外部注入：WallpaperApp 与这里共用同一个实例，
        # 避免在同一份 cfg 上重复跑 migrate_legacy。独立使用时才自己建一个。
        self.manager = manager if manager is not None else SourceManager(cfg)
        self.on_changed = on_changed or (lambda save=False: None)
        self.on_status = on_status or (lambda text, kind="ready": None)
        self.selected_id = cfg.get("source_id", "all")
        self._row_widgets = {}
        self._drag_source_id = None
        self._test_generation = 0
        self._build()
        self.refresh()

    def _build(self):
        self.parent.grid_columnconfigure(0, weight=0, minsize=360)
        self.parent.grid_columnconfigure(1, weight=1)
        self.parent.grid_rowconfigure(0, weight=1)

        card, body = make_card(self.parent, "图源列表", "拖动右侧把手调整优先级；关闭开关后，该图源不会作为自动回退图源。")
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=8)

        self.list_frame = ctk.CTkScrollableFrame(body, fg_color="transparent")
        self.list_frame.pack(fill=tk.BOTH, expand=True)

        ctk.CTkButton(body, text="＋ 新建自定义图源", height=38, command=self.new_source).pack(fill=tk.X, pady=(10, 0))

        card, body = make_card(self.parent, "图源编辑器", "每个自定义图源都可以单独设置 URL、尺寸、参数与网络重试。")
        card.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=8)

        self.editor_title = ctk.CTkLabel(body, text="选择一个图源开始编辑", font=theme.FONT_HEADING, anchor="w")
        self.editor_title.pack(fill=tk.X, pady=(0, 12))

        self.edit_name, self._name_entry = self._field(body, "名称", "我的随机壁纸")
        self.edit_url, self._url_entry = self._field(body, "URL", "https://example.com/random?size={size}")

        grid = ctk.CTkFrame(body, fg_color="transparent")
        grid.pack(fill=tk.X, pady=5)
        grid.grid_columnconfigure((0, 1), weight=1)
        self.edit_site, self._site_combo = self._combo(grid, "{site} 参数", ["all", "konachan", "yandere"], 0)
        self.edit_size, self._size_combo = self._combo(grid, "{size} 参数", ["pc", "mobile"], 1)

        grid2 = ctk.CTkFrame(body, fg_color="transparent")
        grid2.pack(fill=tk.X, pady=5)
        grid2.grid_columnconfigure((0, 1), weight=1)
        self.edit_timeout, self._timeout_entry = self._entry(grid2, "超时（秒）", "15", 0)
        self.edit_retries, self._retries_entry = self._entry(grid2, "失败重试次数", "3", 1)

        # 随"内置图源只读 / 自定义图源可编辑"切换的控件，显式列出来并带上各自
        # 可编辑时的 state。不能靠遍历控件树去猜：图源列表卡片里将来一旦出现
        # 输入框就会被误禁用。
        #
        # 下拉框可编辑时必须是 "readonly" 而不是 "normal"——后者允许自由输入，
        # 用户就能把 {site} / {size} 填成列表以外的值。
        self._editor_controls = (
            (self._name_entry, "normal"),
            (self._url_entry, "normal"),
            (self._site_combo, "readonly"),
            (self._size_combo, "readonly"),
            (self._timeout_entry, "normal"),
            (self._retries_entry, "normal"),
        )

        self.edit_enabled = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(body, text="启用这个图源", variable=self.edit_enabled).pack(anchor=tk.W, pady=(8, 4))
        ctk.CTkLabel(body, text="支持：直接返回图片、302 跳转图片，或返回 {\"url\": \"图片地址\"}。占位符 {size} / {site} 会自动替换。",
                     justify="left", wraplength=520, text_color=theme.COLOR_MUTED).pack(anchor=tk.W, pady=(5, 12))

        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.pack(fill=tk.X, pady=(4, 0))
        ctk.CTkButton(buttons, text="测试图源", height=38, command=self.test_source).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        ctk.CTkButton(buttons, text="保存图源", height=38, command=self.save).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ctk.CTkButton(buttons, text="删除图源", height=38, fg_color="#8c4b4b", hover_color="#6d3838", command=self.delete).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

    # 下面三个构造器都返回 (变量, 控件)：控件是 _set_editor_state 需要的。
    @staticmethod
    def _field(parent, label, placeholder):
        r = ctk.CTkFrame(parent, fg_color="transparent")
        r.pack(fill=tk.X, pady=4)
        ctk.CTkLabel(r, text=label, width=80, anchor="w").pack(side=tk.LEFT)
        var = tk.StringVar()
        entry = ctk.CTkEntry(r, textvariable=var, placeholder_text=placeholder)
        entry.pack(side=tk.RIGHT, fill=tk.X, expand=True)
        return var, entry

    @staticmethod
    def _entry(parent, label, default, col):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=0, column=col, sticky="ew", padx=4)
        ctk.CTkLabel(frame, text=label, anchor="w").pack(anchor=tk.W)
        var = tk.StringVar(value=default)
        entry = ctk.CTkEntry(frame, textvariable=var)
        entry.pack(fill=tk.X, pady=(4, 0))
        return var, entry

    @staticmethod
    def _combo(parent, label, values, col):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=0, column=col, sticky="ew", padx=4)
        ctk.CTkLabel(frame, text=label, anchor="w").pack(anchor=tk.W)
        var = tk.StringVar(value=values[0])
        combo = ctk.CTkComboBox(frame, variable=var, values=values, state="readonly")
        combo.pack(fill=tk.X, pady=(4, 0))
        return var, combo

    def _row(self, source):
        row = ctk.CTkFrame(self.list_frame, corner_radius=10, border_width=1)
        row.pack(fill=tk.X, pady=4)
        row.bind("<ButtonPress-1>", lambda e, sid=source["id"]: self._drag_start(e, sid))
        row.bind("<ButtonRelease-1>", lambda e, sid=source["id"]: self._drag_end(e, sid))
        name = ctk.CTkLabel(row, text=source["name"], anchor="w", font=("Microsoft YaHei", 11, "bold"))
        name.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 4), pady=10)
        name.bind("<ButtonPress-1>", lambda e, sid=source["id"]: self._drag_start(e, sid))
        name.bind("<ButtonRelease-1>", lambda e, sid=source["id"]: self._drag_end(e, sid))
        state = "内置" if source.get("builtin") else ("启用" if source.get("enabled", True) else "停用")
        ctk.CTkLabel(row, text=state, width=50, text_color=("gray45", "gray65")).pack(side=tk.LEFT)
        if source.get("builtin"):
            ctk.CTkButton(row, text="使用", width=52, height=28, command=lambda sid=source["id"]: self.select(sid)).pack(side=tk.RIGHT, padx=4)
        else:
            enabled = tk.BooleanVar(value=source.get("enabled", True))
            cb = ctk.CTkCheckBox(row, text="", width=26, variable=enabled, command=lambda sid=source["id"], v=enabled: self.toggle(sid, v.get()))
            cb.pack(side=tk.RIGHT, padx=3)
            ctk.CTkButton(row, text="编辑", width=52, height=28, command=lambda sid=source["id"]: self.select(sid)).pack(side=tk.RIGHT, padx=3)
        ctk.CTkLabel(row, text="⋮⋮", width=26, font=("Arial", 18), cursor="hand2").pack(side=tk.RIGHT, padx=2)
        return row

    def refresh(self):
        for widget in self.list_frame.winfo_children():
            widget.destroy()
        self._row_widgets.clear()
        for source in self.manager.all_sources():
            row = self._row(source)
            self._row_widgets[source["id"]] = row
        self._load_editor(self.selected_id)

    def select(self, source_id):
        source = self.manager.get(source_id)
        if not source:
            return
        self.selected_id = source_id
        self.cfg["source_id"] = source_id
        self._load_editor(source_id)
        self.on_changed(save=False)

    def _load_editor(self, source_id):
        source = self.manager.get(source_id)
        if not source:
            self.editor_title.configure(text="选择一个图源开始编辑")
            return
        self.editor_title.configure(text=("内置图源 · " if source.get("builtin") else "自定义图源 · ") + source["name"])
        self.edit_name.set(source["name"])
        self.edit_url.set(source["url"])
        self.edit_site.set(source.get("site", "all"))
        self.edit_size.set(source.get("size", "pc"))
        self.edit_timeout.set(str(source.get("timeout", 15)))
        self.edit_retries.set(str(source.get("retries", 3)))
        self.edit_enabled.set(source.get("enabled", True))
        # 内置图源允许查看/复制参数，但不允许覆盖或删除。
        self._set_editor_state(not source.get("builtin", False))

    def _set_editor_state(self, editable):
        """把编辑器的 6 个控件切成可编辑或只读。

        只作用于显式记录的 ``_editor_controls``。原来的实现是递归遍历整棵
        ``self.parent`` 子树、把所有 ``CTkEntry`` 都改一遍，有两个问题：

        1. 范围过宽——图源列表卡片里将来一旦出现输入框，就会跟着被禁用；
        2. 漏控件——只处理 ``CTkEntry``，site / size 两个 ``CTkComboBox``
           在内置图源下仍然可编辑，与"内置图源只读"的意图不符。
        """
        for control, editable_state in self._editor_controls:
            control.configure(state=editable_state if editable else "disabled")

    def new_source(self):
        self.selected_id = None
        self.editor_title.configure(text="新建自定义图源")
        self._set_editor_state(True)
        self.edit_name.set("")
        self.edit_url.set("")
        self.edit_site.set("all")
        self.edit_size.set("pc")
        self.edit_timeout.set("15")
        self.edit_retries.set("3")
        self.edit_enabled.set(True)
        self.on_status("正在创建新的自定义图源", "ready")

    def save(self):
        current = self.manager.get(self.selected_id) if self.selected_id else None
        if current and current.get("builtin"):
            # 不加这道闸的话，选中内置图源时点"保存图源"会以该内置源的 id
            # 往 cfg["sources"] 里塞一条自定义图源，而 SourceManager.get() 先查
            # 内置表，于是它永远取不到，只会污染候选列表、制造重复 id。
            messagebox.showinfo(
                "提示",
                "内置图源不能修改。请点「＋ 新建自定义图源」新建一个，"
                "或复制它的参数再保存。",
                parent=self.parent,
            )
            return
        name = self.edit_name.get().strip()
        url = self.edit_url.get().strip()
        if not name or not url:
            messagebox.showwarning("提示", "请填写图源名称和 URL。", parent=self.parent)
            return
        try:
            timeout = int(self.edit_timeout.get())
            retries = int(self.edit_retries.get())
            if not 5 <= timeout <= 60:
                raise ValueError("超时必须在 5～60 秒之间。")
            if not 1 <= retries <= 5:
                raise ValueError("重试次数必须在 1～5 次之间。")
            data, _ = self.manager.add_or_update(self.selected_id, name, url, self.edit_site.get(), self.edit_size.get(), timeout, retries, self.edit_enabled.get())
        except Exception as exc:
            messagebox.showwarning("图源无效", str(exc), parent=self.parent)
            return
        self.selected_id = data["id"]
        self.cfg["source_id"] = self.selected_id
        config_store.save_config(self.cfg)
        self.refresh()
        self.on_changed(save=False)
        self.on_status(f"已保存图源：{name}", "ready")

    def delete(self):
        source = self.manager.get(self.selected_id)
        if not source or source.get("builtin"):
            messagebox.showinfo("提示", "内置图源不能删除。可以新建一个自定义图源替代它。", parent=self.parent)
            return
        if not messagebox.askyesno("确认删除", f"确定删除自定义图源“{source['name']}”吗？", parent=self.parent):
            return
        self.manager.delete(self.selected_id)
        self.selected_id = "all"
        self.cfg["source_id"] = "all"
        config_store.save_config(self.cfg)
        self.refresh()
        self.on_changed(save=False)
        self.on_status("已删除自定义图源", "ready")

    def toggle(self, source_id, enabled):
        self.manager.set_enabled(source_id, enabled)
        # 至少保留当前选中的源可用：如果用户关闭当前源，自动切到第一个启用源。
        if source_id == self.selected_id and not enabled:
            candidates = self.manager.enabled_candidates()
            self.selected_id = candidates[0]["id"] if candidates else "all"
            self.cfg["source_id"] = self.selected_id
        config_store.save_config(self.cfg)
        self.refresh()
        self.on_changed(save=False)

    def _drag_start(self, event, source_id):
        source = self.manager.get(source_id)
        if not source or source.get("builtin"):
            return
        self._drag_source_id = source_id

    def _drag_end(self, event, source_id):
        if self._drag_source_id != source_id:
            return
        self._drag_source_id = None
        row = self._row_widgets.get(source_id)
        if row is None:
            return
        center = event.y_root
        target = None
        for idx, source in enumerate(self.manager.custom_sources()):
            widget = self._row_widgets.get(source["id"])
            if widget is None:
                continue
            midpoint = widget.winfo_rooty() + widget.winfo_height() / 2
            if center < midpoint:
                target = idx
                break
        if target is None:
            target = len(self.manager.custom_sources()) - 1
        if self.manager.move(source_id, target):
            config_store.save_config(self.cfg)
            self.refresh()
            self.on_changed(save=False)
            self.on_status("已调整图源优先级", "ready")

    def test_source(self):
        source = self.manager.get(self.selected_id)
        if source is None or source.get("builtin"):
            source = {
                "id": "test",
                "name": self.edit_name.get().strip() or "新图源",
                "url": self.edit_url.get().strip(),
                "site": self.edit_site.get(),
                "size": self.edit_size.get(),
                "timeout": int(self.edit_timeout.get() or 15),
                "retries": int(self.edit_retries.get() or 2),
            }
        else:
            source = dict(source)
            source["name"] = self.edit_name.get().strip() or source["name"]
            source["url"] = self.edit_url.get().strip()
            source["site"] = self.edit_site.get()
            source["size"] = self.edit_size.get()
        try:
            timeout = max(5, min(60, int(self.edit_timeout.get())))
            retries = max(1, min(5, int(self.edit_retries.get())))
            url = downloader.build_source_url(source["url"], site=source.get("site", "all"), size=source.get("size", "pc"))
        except Exception as exc:
            messagebox.showwarning("无法测试", str(exc), parent=self.parent)
            return
        self.on_status("正在测试图源…", "busy")
        self._test_generation += 1
        generation = self._test_generation

        def task():
            try:
                downloader.fetch_source_image(url, timeout=timeout, retries=retries)
                result = ("source_test_ok", f"图源测试成功：{source['name']}")
            except Exception as exc:
                result = ("source_test_error", f"图源测试失败：{exc}")
            self.parent.after(0, lambda: self._finish_test(generation, *result))

        threading.Thread(target=task, name="source-test", daemon=True).start()

    def _finish_test(self, generation, event, text):
        if generation != self._test_generation:
            return
        self.on_status(text, "ready" if event == "source_test_ok" else "error")
        if event == "source_test_ok":
            messagebox.showinfo("测试成功", text, parent=self.parent)
        else:
            messagebox.showerror("测试失败", text, parent=self.parent)
