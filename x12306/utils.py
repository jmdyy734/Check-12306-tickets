#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
@author: HJK
@file: utils.py
@time: 2019-02-08
"""

import os
import platform
import re
import unicodedata

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def colorize(s, color):
    colors = {
        "red": "\033[31m",
        "green": "\033[32m",
        "yellow": "\033[33m",
        "blue": "\033[34m",
        "pink": "\033[35m",
        "cyan": "\033[36m",
        "gray": "\033[90m",
        # 高铁
        "g": "\033[91m",
        # 普通列车
        "o": "\033[92m",
        # 动车
        "d": "\033[93m",
        # 城际
        "c": "\033[93m",
    }
    if color not in colors:
        return str(s)
    # Windows 控制台默认不输出颜色；GUI 运行时设置 X12306_ANSI=1，
    # 由 GUI 把 ANSI 码渲染成彩色文字
    if platform.system() == "Windows" and not os.environ.get("X12306_ANSI"):
        return str(s)
    return colors[color] + str(s) + "\033[0m"


def display_width(s):
    """字符串的显示宽度：ASCII 计 1，中文等全角字符计 2，忽略 ANSI 颜色码"""
    s = ANSI_RE.sub("", str(s))
    width = 0
    for ch in s:
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            width += 2
        else:
            width += 1
    return width


def pad_to_width(s, width, align="center"):
    """按显示宽度把字符串补到指定宽度（用于表格对齐）"""
    gap = width - display_width(s)
    if gap <= 0:
        return s
    if align == "left":
        return s + " " * gap
    if align == "right":
        return " " * gap + s
    left = gap // 2
    return " " * left + s + " " * (gap - left)


def format_table(headers, rows, aligns=None):
    """把表头和数据行渲染成纯文本表格，正确处理中文宽字符和 ANSI 颜色码"""
    aligns = aligns or []
    widths = [display_width(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            w = display_width(cell)
            if w > widths[i]:
                widths[i] = w

    def border():
        return "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    def fmt_row(cells):
        parts = []
        for i, cell in enumerate(cells):
            align = aligns[i] if i < len(aligns) else "center"
            parts.append(pad_to_width(str(cell), widths[i], align))
        return "| " + " | ".join(parts) + " |"

    lines = [border(), fmt_row(headers), border()]
    for row in rows:
        lines.append(fmt_row(row))
        lines.append(border())
    return "\n".join(lines)
