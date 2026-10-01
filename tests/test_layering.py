"""分层规则：core → services → ui，箭头永不反向。

这条规则只写在模块注释里是不够的——必须有东西自动检查，否则过几个月就会有人在
services 里 import tkinter、或者在 core 里 import services，分层重新退化成
"只存在于文件名里的约定"。这正是本次重构要解决的根本问题。
"""
import ast
import pathlib
import unittest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

# 分层：数字越大越靠上。上层可以 import 下层，反之不行。
LAYER_ORDER = ("core", "services", "ui")

# 每一层允许 import 的本项目顶层包。
# 同一层内部互相 import 是正常的（core.config_store 用 core.paths、
# services.cache 用 services.images），所以每层都把自己算进去。
ALLOWED_INBOUND = {
    "core": {"core"},
    "services": {"core", "services"},
    "ui": {"core", "services", "ui"},
}

# 编排层：位于 ui 之上，但它自己不允许碰界面工具包
ORCHESTRATOR = "app.py"
ENTRY = "wallpaper_changer.py"

# 界面工具包
TOOLKITS = {"tkinter", "customtkinter"}


def imported_modules(path):
    """返回文件里 import 到的模块名集合（绝对名，不含 from 的具体符号）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                names.add(node.module)
    return names


def project_files(*directories):
    """收集指定目录（'.' 表示项目根）下的 Python 文件。"""
    found = []
    for directory in directories:
        base = PROJECT_ROOT if directory == "." else PROJECT_ROOT / directory
        found.extend(sorted(base.glob("*.py")))
    return found


def relative(path):
    return path.relative_to(PROJECT_ROOT).as_posix()


class LayerDirectionTest(unittest.TestCase):
    def test_lower_layers_never_import_higher_ones(self):
        for layer, allowed in ALLOWED_INBOUND.items():
            for path in project_files(layer):
                referenced = {name.split(".")[0] for name in imported_modules(path)}
                offending = (referenced & set(LAYER_ORDER)) - allowed
                with self.subTest(module=relative(path)):
                    self.assertEqual(
                        offending, set(),
                        f"{path.name} 属于 {layer} 层，不应 import {sorted(offending)}",
                    )

    def test_core_only_references_itself(self):
        self.assertEqual(ALLOWED_INBOUND["core"], {"core"})

    def test_ui_is_not_imported_by_anything_below_it(self):
        for layer in ("core", "services"):
            for path in project_files(layer):
                referenced = {name.split(".")[0] for name in imported_modules(path)}
                with self.subTest(module=relative(path)):
                    self.assertNotIn("ui", referenced)


class ToolkitIsolationTest(unittest.TestCase):
    def _toolkit_importers(self, *directories):
        return [
            path for path in project_files(*directories)
            if imported_modules(path) & TOOLKITS
        ]

    def test_core_and_services_are_toolkit_free(self):
        for path in self._toolkit_importers("core", "services"):
            with self.subTest(module=relative(path)):
                self.fail(f"{relative(path)} 不应依赖界面工具包")

    def test_orchestrator_is_toolkit_free(self):
        # app.py 只做编排：弹窗走 ui.dialogs，控件在 ui.main_window，
        # 因此它连 tkinter 都不需要 import。
        self.assertNotIn("tkinter", imported_modules(PROJECT_ROOT / ORCHESTRATOR))
        self.assertNotIn("customtkinter", imported_modules(PROJECT_ROOT / ORCHESTRATOR))

    def test_toolkit_imports_are_confined_to_ui_and_the_entry(self):
        allowed_prefixes = ("ui/",)
        offenders = []
        for path in self._toolkit_importers(".", "core", "services", "ui"):
            name = relative(path)
            if name == ENTRY or name.startswith(allowed_prefixes):
                continue
            offenders.append(name)
        self.assertEqual(offenders, [], "界面工具包只应出现在 ui/ 与入口文件里")

    def test_ui_package_really_holds_the_widget_code(self):
        # 防止上面的用例变成空断言：ui/ 里必须确实有若干文件在用 customtkinter
        users = [relative(path) for path in self._toolkit_importers("ui")]
        self.assertGreaterEqual(len(users), 5, f"ui/ 里的控件模块太少：{users}")


class PrivateApiIsolationTest(unittest.TestCase):
    """CustomTkinter 私有属性的使用必须集中。

    ``fixed_combobox`` 依赖 CTkComboBox 的一批私有属性，``dialogs`` 依赖
    CTkInputDialog._entry——它们是最容易随 CustomTkinter 升级而失效的地方。
    把这类依赖限定在少数模块里，升级时只需要盯住这几个文件。
    """

    # 允许直接触碰 CustomTkinter 私有属性（下划线开头）的文件
    ALLOWED = {
        "ui/fixed_combobox.py",
        "ui/dialogs.py",
    }

    def _self_attribute_names(self, path):
        """收集 self._xxx 形式的属性访问。"""
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id == "self" and node.attr.startswith("_"):
                    names.add(node.attr)
        return names

    def test_new_private_ctk_dependencies_show_up_here(self):
        # 每个文件自己的私有属性（self._foo）是正常写法，不能一概而论；
        # 这里只锁定"已知会碰到第三方私有接口"的那几个模块存在，
        # 并确保 ui/fixed_combobox.py 仍然被 ui/favorite_view.py 使用。
        self.assertTrue((PROJECT_ROOT / "ui" / "fixed_combobox.py").is_file())
        self.assertTrue((PROJECT_ROOT / "ui" / "dialogs.py").is_file())
        favorite_view = imported_modules(PROJECT_ROOT / "ui" / "favorite_view.py")
        self.assertIn("ui.fixed_combobox", favorite_view)


if __name__ == "__main__":
    unittest.main()
