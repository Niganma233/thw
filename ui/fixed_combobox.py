"""固定高度的下拉选择框。

CTkComboBox 的下拉列表是一个原生 tkinter.Menu，收藏一多就会把全部项目一次性铺开，
也会盖住下面的界面。这个模块在 CTkComboBox 的基础上把下拉列表换成固定高度的可滚动
列表：最多显示 ``max_visible_items`` 项（默认 8 项），并且弹出列表的宽度、左边缘与
控件本身完全一致，从而和上方控件对齐。
"""

import tkinter as tk

import customtkinter as ctk


class FixedHeightComboBox(ctk.CTkComboBox):
    """外观与 CTkComboBox 相同、下拉列表高度固定的选择框。

    除 ``max_visible_items`` / ``popup_min_width`` 外，其余参数与 ``CTkComboBox`` 一致
    （``values``、``variable``、``command``、``state``、``dropdown_font`` 等）。
    """

    def __init__(self, master, max_visible_items: int = 8, popup_min_width: int = 160, **kwargs):
        super().__init__(master, **kwargs)

        self._max_visible_items = max(1, int(max_visible_items))
        self._popup_min_width = popup_min_width
        self._popup = None
        self._popup_list = None
        self._popup_scrollbar = None
        self._hover_index = None
        self._popup_anchor = None
        self._popup_bindings = []

        # 点击输入框区域也可以展开列表（默认只有右侧箭头能展开）
        self.bind("<Button-1>", self._clicked)

    # ---------- 对外接口 ----------
    def close_dropdown(self):
        """关闭下拉列表（未展开时什么也不做）。"""
        self._close_popup()

    def is_dropdown_open(self) -> bool:
        return self._popup is not None

    # ---------- 展开 / 关闭 ----------
    def _clicked(self, event=None):
        if self._state == tk.DISABLED or not self._values:
            return
        if self._popup is not None:
            self._close_popup()
        else:
            self._open_dropdown_menu()

    def _open_dropdown_menu(self):
        if self._popup is not None or self._state == tk.DISABLED or not self._values:
            return

        fg_color, hover_color, text_color, border_color = self._dropdown_colors()
        font = self._apply_font_scaling(self._dropdown_menu.cget("font"))
        visible_rows = min(len(self._values), self._max_visible_items)

        popup = tk.Toplevel(self)
        popup.withdraw()
        popup.overrideredirect(True)
        popup.configure(bg=border_color)
        try:
            popup.attributes("-topmost", True)
        except tk.TclError:
            pass

        content = tk.Frame(popup, bg=fg_color, bd=0, highlightthickness=0)
        content.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        listbox = tk.Listbox(
            content,
            activestyle="none",
            bd=0,
            highlightthickness=0,
            relief=tk.FLAT,
            exportselection=False,
            selectmode=tk.BROWSE,
            font=font,
            height=visible_rows,
            width=1,
            takefocus=0,
            background=fg_color,
            foreground=text_color,
            selectbackground=hover_color,
            selectforeground=text_color,
            disabledforeground=text_color,
        )
        for value in self._values:
            listbox.insert(tk.END, value)

        scrollbar = None
        if len(self._values) > visible_rows:
            scrollbar = ctk.CTkScrollbar(content, command=listbox.yview, width=12)
            listbox.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 2), pady=2)
        # 左侧留出与输入框文字相同的内边距，列表文字和选择框文字对齐
        text_inset = self._apply_widget_scaling(max(self._corner_radius, 3))
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(text_inset, 0))

        self._popup = popup
        self._popup_list = listbox
        self._popup_scrollbar = scrollbar

        self._select_current_value()
        self._bind_popup_events(popup, listbox)

        self._place_popup(popup, listbox)
        self._popup_anchor = self._anchor()

        popup.deiconify()
        popup.lift()
        try:
            listbox.focus_set()
        except tk.TclError:
            pass

    def _place_popup(self, popup, listbox):
        """把弹出列表放在控件正下方：左边缘对齐、宽度一致；空间不够时向上展开。"""
        popup.update_idletasks()

        width = max(self.winfo_width(), self._apply_widget_scaling(self._popup_min_width))
        height = listbox.winfo_reqheight() + 2  # 上下各 1px 边框

        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height() + 2

        screen_width = popup.winfo_screenwidth()
        screen_height = popup.winfo_screenheight()
        if x + width > screen_width:
            x = max(0, screen_width - width)
        if y + height > screen_height:
            above = self.winfo_rooty() - height - 2
            y = above if above >= 0 else max(0, screen_height - height)

        popup.geometry(f"{int(width)}x{int(height)}+{int(x)}+{int(y)}")

    def _close_popup(self):
        popup, self._popup = self._popup, None
        self._popup_list = None
        self._popup_scrollbar = None
        self._hover_index = None
        self._popup_anchor = None

        for widget, sequence, funcid in self._popup_bindings:
            try:
                widget.unbind(sequence, funcid)
            except Exception:
                pass
        self._popup_bindings = []

        if popup is not None:
            try:
                popup.destroy()
            except Exception:
                pass

    # ---------- 弹出列表事件 ----------
    def _bind_popup_events(self, popup, listbox):
        root = self.winfo_toplevel()
        self._popup_bindings = [
            (root, "<Button-1>", root.bind("<Button-1>", self._on_any_click, add="+")),
            (root, "<Unmap>", root.bind("<Unmap>", self._on_root_unmap, add="+")),
            (root, "<Configure>", root.bind("<Configure>", self._on_root_configure, add="+")),
        ]

        listbox.bind("<ButtonRelease-1>", self._on_list_click)
        listbox.bind("<Motion>", self._on_list_motion)
        listbox.bind("<Return>", self._on_list_confirm)
        listbox.bind("<KP_Enter>", self._on_list_confirm)
        listbox.bind("<Escape>", lambda _event: self._close_popup())
        listbox.bind("<Up>", lambda _event: self._move_selection(-1))
        listbox.bind("<Down>", lambda _event: self._move_selection(1))
        listbox.bind("<MouseWheel>", self._on_mouse_wheel)

        popup.bind("<Escape>", lambda _event: self._close_popup())
        popup.bind("<MouseWheel>", self._on_mouse_wheel)
        popup.bind("<FocusOut>", self._on_popup_focus_out)

    def _on_any_click(self, event):
        if self._popup is None:
            return
        widget = event.widget
        if widget is self._canvas or widget is self._entry:
            return  # 点击控件本身由 _clicked 负责
        if widget is self._popup or str(widget).startswith(str(self._popup) + "."):
            return
        self._close_popup()

    def _on_root_unmap(self, event):
        if event.widget is self.winfo_toplevel():
            self._close_popup()

    def _anchor(self):
        """控件在屏幕上的位置与尺寸，用于判断窗口是否移动/缩放过。"""
        return (self.winfo_rootx(), self.winfo_rooty(), self.winfo_width(), self.winfo_height())

    def _on_root_configure(self, event):
        # 窗口移动或缩放后弹出列表的位置就失效了，直接关闭；
        # 其余 Configure（子控件重绘）不影响，锚点没变就保持展开。
        if self._popup is None or event.widget is not self.winfo_toplevel():
            return
        self.after_idle(self._close_popup_if_moved)

    def _close_popup_if_moved(self):
        if self._popup is not None and self._anchor() != self._popup_anchor:
            self._close_popup()

    def _on_popup_focus_out(self, event=None):
        if self._popup is not None:
            self._popup.after_idle(self._close_popup_if_focus_lost)

    def _close_popup_if_focus_lost(self):
        if self._popup is None or not self._popup.winfo_exists():
            return
        try:
            focused = self.focus_get()
        except Exception:
            focused = None
        if focused is None:
            return
        if focused is self._popup or str(focused).startswith(str(self._popup) + "."):
            return
        self._close_popup()

    def _on_list_motion(self, event):
        index = self._popup_list.nearest(event.y)
        if index == self._hover_index:
            return
        self._hover_index = index
        self._popup_list.selection_clear(0, tk.END)
        self._popup_list.selection_set(index)
        self._popup_list.activate(index)

    def _on_list_click(self, event):
        if self._popup_list is None:
            return
        self._choose_index(self._popup_list.nearest(event.y))

    def _on_list_confirm(self, event=None):
        if self._popup_list is None:
            return "break"
        selection = self._popup_list.curselection()
        index = selection[0] if selection else self._popup_list.index(tk.ACTIVE)
        self._choose_index(index)
        return "break"

    def _on_mouse_wheel(self, event):
        if self._popup_list is None:
            return
        self._popup_list.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def _move_selection(self, step):
        if self._popup_list is None:
            return "break"
        selection = self._popup_list.curselection()
        index = selection[0] if selection else 0
        index = max(0, min(len(self._values) - 1, index + step))
        self._hover_index = index
        self._popup_list.selection_clear(0, tk.END)
        self._popup_list.selection_set(index)
        self._popup_list.activate(index)
        self._popup_list.see(index)
        return "break"

    def _select_current_value(self):
        current = self.get()
        if current in self._values:
            index = self._values.index(current)
            self._hover_index = index
            self._popup_list.selection_set(index)
            self._popup_list.activate(index)
            self._popup_list.see(index)

    def _choose_index(self, index):
        if index is None or not (0 <= index < len(self._values)):
            self._close_popup()
            return
        value = self._values[index]
        self._close_popup()
        self._dropdown_callback(value)  # 更新输入框并触发 command

    # ---------- 颜色 / 生命周期 ----------
    def _dropdown_colors(self):
        """从主题里取出下拉列表配色，保证与 CTkComboBox 的下拉菜单外观一致。"""
        menu = self._dropdown_menu
        fg_color = self._apply_appearance_mode(menu.cget("fg_color"))
        hover_color = self._apply_appearance_mode(menu.cget("hover_color"))
        text_color = self._apply_appearance_mode(menu.cget("text_color"))
        # 弹出列表的 1px 边框沿用控件本身的边框色
        border_color = self._apply_appearance_mode(self._border_color)
        return fg_color, hover_color, text_color, border_color

    def configure(self, require_redraw=False, **kwargs):
        if "values" in kwargs:
            self._close_popup()  # 选项变化后弹出列表已失效
        super().configure(require_redraw=require_redraw, **kwargs)

    def destroy(self):
        self._close_popup()
        super().destroy()
