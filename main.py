# -*- coding: utf-8 -*-
"""程序入口：加载配置，启动界面。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui import KBApp  # noqa: E402


def main() -> None:
    app = KBApp()
    app.mainloop()


if __name__ == "__main__":
    main()
