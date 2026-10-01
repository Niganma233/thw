"""界面层：所有 CustomTkinter 控件都集中在这里。

与上层/下层的约定：

* 本包可以 import ``services`` 与 ``core``，也可以 import ``config``；
* ``services`` 与 ``core`` **不得**反过来 import 本包（Phase 7 会加
  tests/test_layering.py 把这条规则钉死）；
* 全局外观由 ``ui.theme.apply()`` 设置，必须在创建任何控件之前调用一次。
"""
