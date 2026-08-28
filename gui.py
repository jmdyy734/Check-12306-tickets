#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
x12306 查票工具 - 图形界面（学习用途，请勿高频查询）

运行方式：
  1. 任意电脑：双击 查票工具.exe（单文件，无需安装任何环境）
  2. 本机有 Python3.9：双击 启动查票工具.bat

说明：结果表第一列"车次"是每趟车的车次号（如 G6058），不需要填写。
"""

import contextlib
import datetime
import io
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import traceback

import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

# 打包成 exe 后 sys.frozen 为 True，BASE_DIR 为 exe 所在目录
FROZEN = getattr(sys, "frozen", False)
BASE_DIR = (os.path.dirname(sys.executable) if FROZEN
            else os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import x12306
from x12306.__version__ import __version__
from x12306.settings import SEAT_TYPES
from x12306.update_station import update_station

MAIN_PY = os.path.join(BASE_DIR, "x12306.py")
CONFIG_FILE = os.path.join(BASE_DIR, "gui_config.json")
ERROR_LOG = os.path.join(BASE_DIR, "gui_error.log")
DEFAULT_STATIONS_FILE = os.path.join(BASE_DIR, "x12306", "data", "stations.txt")

SEAT_OPTIONS = list(SEAT_TYPES.keys())
# 一个座位都不勾选时，显示全部座位类型
ALL_SEATS = " ".join(SEAT_TYPES.keys())

# ANSI 颜色码 → tk 文字颜色，查询输出中的颜色会渲染成彩色文字
ANSI_RE = re.compile(r"\x1b\[([0-9;]*)m")
ANSI_COLORS = {
    "31": "#d73027",  # red（无票）
    "32": "#1a9850",  # green（有票）
    "33": "#b8860b",  # yellow（动车/城际车次）
    "90": "#999999",  # gray（该车次没有此座位）
    "91": "#d73027",  # 高铁车次
    "92": "#1a9850",  # 普通列车车次
    "93": "#b8860b",  # 动车/城际车次
}

# 省份 → 城市对照表。城市名来自 stations.txt 的"所属城市"字段；
# 没收录到的城市会自动归入"其他"，不影响使用。
PROVINCE_ORDER = [
    "北京", "天津", "上海", "重庆", "河北", "山西", "内蒙古", "辽宁", "吉林",
    "黑龙江", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北",
    "湖南", "广东", "广西", "海南", "四川", "贵州", "云南", "西藏", "陕西",
    "甘肃", "青海", "宁夏", "新疆", "香港", "台湾", "澳门", "老挝",
]

PROVINCE_CITIES = {
    "北京": ["北京"],
    "天津": ["天津"],
    "上海": ["上海"],
    "重庆": ["重庆", "万州", "涪陵", "黔江", "合川", "永川", "江津", "大足",
             "璧山", "荣昌", "潼南", "垫江", "梁平", "丰都", "云阳", "奉节",
             "巫山", "石柱", "石柱县", "秀山", "酉阳", "彭水", "武隆", "长寿",
             "綦江"],
    "河北": ["石家庄", "唐山", "秦皇岛", "邯郸", "邢台", "保定", "张家口",
             "承德", "沧州", "廊坊", "衡水"],
    "山西": ["太原", "大同", "阳泉", "长治", "晋城", "朔州", "晋中", "运城",
             "忻州", "临汾", "吕梁"],
    "内蒙古": ["呼和浩特", "包头", "乌海", "赤峰", "通辽", "鄂尔多斯",
               "呼伦贝尔", "巴彦淖尔", "乌兰察布", "兴安", "锡林郭勒",
               "阿拉善", "二连浩特"],
    "辽宁": ["沈阳", "大连", "鞍山", "抚顺", "本溪", "丹东", "锦州", "营口",
             "阜新", "辽阳", "盘锦", "铁岭", "朝阳", "葫芦岛"],
    "吉林": ["长春", "吉林", "四平", "辽源", "通化", "白山", "松原", "白城",
             "延边"],
    "黑龙江": ["哈尔滨", "齐齐哈尔", "鸡西", "鹤岗", "双鸭山", "大庆", "伊春",
               "佳木斯", "七台河", "牡丹江", "黑河", "绥化", "加格达奇",
               "桦南", "林口", "马桥河"],
    "江苏": ["南京", "无锡", "徐州", "常州", "苏州", "南通", "连云港", "淮安",
             "盐城", "扬州", "镇江", "泰州", "宿迁", "仪征"],
    "浙江": ["杭州", "宁波", "温州", "嘉兴", "湖州", "绍兴", "金华", "衢州",
             "台州", "丽水"],
    "安徽": ["合肥", "芜湖", "蚌埠", "淮南", "马鞍山", "淮北", "铜陵", "安庆",
             "黄山", "滁州", "阜阳", "宿州", "六安", "亳州", "池州", "宣城",
             "凤阳"],
    "福建": ["福州", "厦门", "莆田", "三明", "泉州", "漳州", "南平", "龙岩",
             "宁德", "沙县", "上杭", "安溪", "长汀", "建宁", "来舟", "麦园"],
    "江西": ["南昌", "景德镇", "萍乡", "九江", "新余", "鹰潭", "赣州", "吉安",
             "宜春", "抚州", "上饶", "临川", "于都", "芦溪", "资溪", "崇仁",
             "江边村"],
    "山东": ["济南", "青岛", "淄博", "枣庄", "东营", "烟台", "潍坊", "济宁",
             "泰安", "威海", "日照", "临沂", "德州", "聊城", "滨州", "菏泽",
             "莱芜"],
    "河南": ["郑州", "开封", "洛阳", "平顶山", "安阳", "鹤壁", "新乡", "焦作",
             "濮阳", "许昌", "漯河", "三门峡", "南阳", "商丘", "信阳", "周口",
             "驻马店", "济源"],
    "湖北": ["武汉", "黄石", "十堰", "宜昌", "襄阳", "鄂州", "荆门", "孝感",
             "荆州", "黄冈", "咸宁", "随州", "恩施", "仙桃", "潜江", "天门",
             "神农架", "武穴", "浠水", "蕲春"],
    "湖南": ["长沙", "株洲", "湘潭", "衡阳", "邵阳", "岳阳", "常德", "张家界",
             "益阳", "郴州", "永州", "怀化", "娄底", "吉首", "邵东"],
    "广东": ["广州", "韶关", "深圳", "珠海", "汕头", "佛山", "江门", "湛江",
             "茂名", "肇庆", "惠州", "梅州", "汕尾", "河源", "阳江", "清远",
             "东莞", "中山", "潮州", "揭阳", "云浮"],
    "广西": ["南宁", "柳州", "桂林", "梧州", "北海", "防城港", "钦州", "贵港",
             "玉林", "百色", "贺州", "河池", "来宾", "崇左"],
    "海南": ["海口", "三亚", "儋州", "文昌", "琼海", "万宁", "东方", "澄迈",
             "临高", "昌江", "乐东", "陵水"],
    "四川": ["成都", "自贡", "攀枝花", "泸州", "德阳", "绵阳", "广元", "遂宁",
             "内江", "乐山", "南充", "眉山", "宜宾", "广安", "达州", "雅安",
             "巴中", "资阳", "阿坝藏族羌族自治州", "西昌", "达川"],
    "贵州": ["贵阳", "六盘水", "遵义", "安顺", "毕节", "铜仁", "兴义", "凯里",
             "都匀"],
    "云南": ["昆明", "曲靖", "玉溪", "保山", "昭通", "丽江", "普洱", "临沧",
             "楚雄", "文山", "大理", "蒙自", "个旧", "景洪", "香格里拉",
             "漾濞", "南涧", "墨江", "宁洱", "元江", "峨山", "勐腊", "永平"],
    "西藏": ["拉萨", "日喀则", "林芝", "山南", "那曲", "岗嘎", "加查", "桑日",
             "扎囊", "贡嘎", "米林", "朗县"],
    "陕西": ["西安", "铜川", "宝鸡", "咸阳", "渭南", "延安", "汉中", "榆林",
             "安康", "商洛", "华阴", "富平", "蒲城"],
    "甘肃": ["兰州", "嘉峪关", "金昌", "白银", "天水", "武威", "张掖", "平凉",
             "酒泉", "庆阳", "定西", "陇南", "玉门"],
    "青海": ["西宁", "海东", "海北州", "海西州", "德令哈", "格尔木", "茫崖"],
    "宁夏": ["银川", "石嘴山", "吴忠", "固原", "中卫", "灵武", "青铜峡"],
    "新疆": ["乌鲁木齐", "克拉玛依", "吐鲁番", "哈密", "昌吉",
             "巴音郭楞蒙古自治州", "阿克苏", "喀什", "和田", "伊宁", "塔城",
             "阿勒泰", "阿图什", "博乐", "库尔勒", "石河子", "铁门关"],
    "香港": ["香港"],
    "老挝": ["万象", "孟赛", "琅勃拉邦", "磨丁", "老挝万荣"],
}


def load_station_data():
    """解析站点数据，返回 (全部站名列表, {城市: [站名列表]}, {省份: [城市列表]})。
    用于出发地/目的地的 省份→城市→站点 级联下拉选择。"""
    st_file = resolve_data_paths()[0] or DEFAULT_STATIONS_FILE
    station_names = []
    seen = set()
    city_stations = {}  # 城市 -> 该城市下的站名（按文件顺序去重）
    with open(st_file, "r", encoding="utf-8") as f:
        for line in f:
            for entry in line.strip().split("@"):
                if not entry:
                    continue
                parts = entry.split("|")
                if len(parts) < 8 or not parts[1]:
                    continue
                name, city = parts[1], parts[7]
                if name not in seen:
                    seen.add(name)
                    station_names.append(name)
                if city:
                    city_stations.setdefault(city, [])
                    if name not in city_stations[city]:
                        city_stations[city].append(name)

    # 城市 -> 省份集合（同名城市允许归入多个省份）
    city_prov = {}
    for prov, cities in PROVINCE_CITIES.items():
        for c in cities:
            if c in city_stations:
                city_prov.setdefault(c, set()).add(prov)

    province_cities = {}
    for prov in PROVINCE_ORDER:
        cs = [c for c in city_stations if prov in city_prov.get(c, ())]
        if cs:
            province_cities[prov] = cs
    rest = [c for c in city_stations if c not in city_prov]
    if rest:
        province_cities["其他"] = rest
    return station_names, city_stations, province_cities


def insert_ansi(widget, text):
    """插入文本，把其中的 ANSI 颜色码渲染成 tk 文字颜色"""
    tag = None
    last = 0
    for m in ANSI_RE.finditer(text):
        widget.insert(tk.END, text[last:m.start()], tag)
        codes = m.group(1).split(";") if m.group(1) else ["0"]
        if "0" not in codes:
            tag = next((ANSI_COLORS[c] for c in codes if c in ANSI_COLORS), None)
        else:
            tag = None
        last = m.end()
    widget.insert(tk.END, text[last:], tag)


def resolve_data_paths():
    """exe 版返回数据文件路径（首次运行从内置包复制到 exe 目录）；
    源码版返回 (None, None, None)，使用包内默认路径"""
    if not FROZEN:
        return None, None, None
    data_dir = os.path.join(BASE_DIR, "x12306", "data")
    os.makedirs(data_dir, exist_ok=True)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled = os.path.join(meipass, "x12306", "data")
        for fn in ("stations.txt", "cdn.txt", "proxies.txt"):
            src = os.path.join(bundled, fn)
            dst = os.path.join(data_dir, fn)
            if os.path.isfile(src) and not os.path.isfile(dst):
                shutil.copy(src, dst)
    return (os.path.join(data_dir, "stations.txt"),
            os.path.join(data_dir, "proxies.txt"),
            os.path.join(data_dir, "cdn.txt"))


def build_command(fs, ts, date, seats, trains_no,
                  remaining, gcd, ktz, verbose, zmode, zzmode):
    """生成等效的命令行命令（用于复制，方便在 CMD 里学习）"""
    cmd = ["py", "-3.9", MAIN_PY, "-f", fs, "-t", ts, "-d", date]
    if seats.strip():
        cmd += ["-s", seats.strip()]
    if trains_no.strip():
        cmd += ["-n", trains_no.strip()]
    if remaining:
        cmd.append("-r")
    if gcd:
        cmd.append("--gcd")
    if ktz:
        cmd.append("--ktz")
    if verbose:
        cmd.append("-v")
    if zmode:
        cmd.append("-z")
    if zzmode:
        cmd.append("-zz")
    return cmd


class QueueWriter:
    """把 print 输出逐行转发到 GUI 队列，实现实时显示"""

    def __init__(self, q):
        self.q = q
        self.buf = ""

    def write(self, s):
        self.buf += s
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            self.q.put(line + "\n")

    def flush(self):
        pass

    def finish(self):
        if self.buf:
            self.q.put(self.buf)
            self.buf = ""


class App:
    def __init__(self, root):
        self.root = root
        root.title("12306 查票工具（学习用途） v" + __version__)
        root.geometry("920x700")
        root.minsize(760, 520)

        self.q = queue.Queue()
        self.running = False
        self.suppress = False

        self.data_paths = resolve_data_paths()
        self.config = self.load_config()
        (self.station_names, self.city_stations,
         self.province_cities) = load_station_data()
        self.build_widgets()
        self.root.after(100, self.poll_queue)

    # ---------- 配置保存 / 读取 ----------
    def load_config(self):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_config(self):
        cfg = {
            "fs": self.fs_var.get().strip(),
            "ts": self.ts_var.get().strip(),
            "seats": [name for name in SEAT_OPTIONS if self.seat_vars[name].get()],
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------- 界面 ----------
    def build_widgets(self):
        pad = {"padx": 6, "pady": 4}

        # 第一行：出发地 / 目的地 / 日期（年月日下拉选择）
        # 出发地/目的地既可以直接输入，也可以点【选】按 省份→城市→站点 级联选择
        row1 = tk.Frame(self.root)
        row1.pack(fill="x", **pad)

        tk.Label(row1, text="出发地：").pack(side="left")
        self.fs_var = tk.StringVar(value=self.config.get("fs", "北京"))
        tk.Entry(row1, textvariable=self.fs_var, width=13).pack(side="left")
        tk.Button(row1, text="选", width=2,
                  command=lambda: self.choose_station(self.fs_var, "选择出发地"),
                  relief="groove").pack(side="left", padx=(2, 10))

        tk.Label(row1, text="目的地：").pack(side="left")
        self.ts_var = tk.StringVar(value=self.config.get("ts", "上海"))
        tk.Entry(row1, textvariable=self.ts_var, width=13).pack(side="left")
        tk.Button(row1, text="选", width=2,
                  command=lambda: self.choose_station(self.ts_var, "选择目的地"),
                  relief="groove").pack(side="left", padx=(2, 10))

        tk.Label(row1, text="日期：").pack(side="left")
        today = datetime.date.today()
        self.year_var = tk.StringVar(value=str(today.year))
        self.month_var = tk.StringVar(value=str(today.month))
        self.day_var = tk.StringVar(value=str(today.day))

        years = [str(today.year + i) for i in range(3)]
        ttk.Combobox(row1, textvariable=self.year_var, values=years, width=5,
                     state="readonly").pack(side="left")
        tk.Label(row1, text="年").pack(side="left")
        ttk.Combobox(row1, textvariable=self.month_var,
                     values=[str(m) for m in range(1, 13)], width=4,
                     state="readonly").pack(side="left")
        tk.Label(row1, text="月").pack(side="left")
        ttk.Combobox(row1, textvariable=self.day_var,
                     values=[str(d) for d in range(1, 32)], width=4,
                     state="readonly").pack(side="left")
        tk.Label(row1, text="日").pack(side="left")

        # 第二行：座位（高铁/动车、普速火车 两个模块）
        row2 = tk.Frame(self.root)
        row2.pack(fill="x", **pad)

        self.seat_vars = {}
        # 默认不勾选任何座位（都不勾选 = 显示全部）；勾选过的座位会保存到配置里
        saved_seats = self.config.get("seats", [])

        group_hsr = ["商务座", "特等座", "一等座", "二等座", "动卧", "无座"]
        group_ktz = ["高级软卧", "软卧", "硬卧", "软座", "硬座", "其他"]

        for group_title, names in (("高铁/动车", group_hsr), ("普速火车", group_ktz)):
            frame = tk.LabelFrame(row2, text=group_title,
                                  font=("Microsoft YaHei", 10, "bold"))
            frame.pack(side="left", padx=(0, 10))
            for i, name in enumerate(names):
                var = tk.BooleanVar(value=name in saved_seats)
                self.seat_vars[name] = var
                tk.Checkbutton(frame, text=name, variable=var,
                               font=("Microsoft YaHei", 10)).grid(
                    row=i // 3, column=i % 3, sticky="w", padx=4, pady=2)
        tk.Label(row2, text="都不勾选 = 显示全部座位",
                 fg="#888888").pack(side="left")

        # 第三行：车次限制 + 过滤条件
        row3 = tk.Frame(self.root)
        row3.pack(fill="x", **pad)

        tk.Label(row3, text="车次限制：").pack(side="left")
        self.trains_var = tk.StringVar()
        tk.Entry(row3, textvariable=self.trains_var, width=16).pack(side="left")
        tk.Label(row3, text="逗号分隔", fg="#888888").pack(side="left", padx=(0, 10))

        self.r_var = tk.BooleanVar(value=True)
        self.gcd_var = tk.BooleanVar(value=False)
        self.ktz_var = tk.BooleanVar(value=False)

        tk.Checkbutton(row3, text="只看有票", variable=self.r_var).pack(side="left")
        tk.Checkbutton(row3, text="只高铁动车", variable=self.gcd_var,
                       command=self.on_gcd).pack(side="left")
        tk.Checkbutton(row3, text="只普速K/T/Z", variable=self.ktz_var,
                       command=self.on_ktz).pack(side="left")

        # 第四行：模式选项
        row4 = tk.Frame(self.root)
        row4.pack(fill="x", **pad)

        self.v_var = tk.BooleanVar(value=False)
        self.z_var = tk.BooleanVar(value=False)
        self.zz_var = tk.BooleanVar(value=False)

        tk.Checkbutton(row4, text="调试", variable=self.v_var).pack(side="left")
        tk.Checkbutton(row4, text="高级模式", variable=self.z_var,
                       font=("Microsoft YaHei", 10, "bold"),
                       fg="#b8860b").pack(side="left")
        tk.Checkbutton(row4, text="终极模式", variable=self.zz_var,
                       font=("Microsoft YaHei", 10, "bold"),
                       fg="#b8860b").pack(side="left")
        tk.Label(row4, text="高级=查沿途中间站余票，终极=查沿途所有站点组合",
                 fg="#b8860b").pack(side="left", padx=8)

        # 按钮行
        row5 = tk.Frame(self.root)
        row5.pack(fill="x", **pad)

        self.query_btn = tk.Button(row5, text="查 询", width=12,
                                   command=self.on_query, bg="#2b7de9", fg="white")
        self.query_btn.pack(side="left", padx=(0, 6))
        tk.Button(row5, text="复制命令", width=10, command=self.on_copy_cmd).pack(side="left", padx=6)
        tk.Button(row5, text="更新站点数据", width=12, command=self.on_update_station).pack(side="left", padx=6)
        tk.Button(row5, text="停止查询", width=10, command=self.on_stop).pack(side="left", padx=6)
        tk.Button(row5, text="清空输出", width=10, command=self.on_clear).pack(side="left", padx=6)

        # 输出区（宋体等宽，保证表格对齐）
        # 只读：可以选中、复制、滚动，但不能直接编辑，清空请用【清空输出】按钮
        self.output = scrolledtext.ScrolledText(self.root, font=("NSimSun", 11),
                                                wrap="none")
        self.output.pack(fill="both", expand=True, padx=6, pady=(2, 6))
        for color in set(ANSI_COLORS.values()):
            self.output.tag_configure(color, foreground=color)
        self.output.insert(tk.END, "提示：选择出发地、目的地、日期和座位，点击【查询】。\n"
                                   "出发地/目的地可手动输入，也可点【选】按 省份→城市→站点 选择。\n"
                                   "结果中的“车次”列是每趟车的车次号，不需要填写。\n"
                                   "结果中每个座位类型单独一列，绿色=有票，红色=无票。\n"
                                   "本工具仅供学习，请勿高频查询，避免账号风控。\n\n")
        self.output.config(state="disabled")

        # 输出区右键菜单：复制 / 全选 / 清空
        self.output_menu = tk.Menu(self.root, tearoff=0)
        self.output_menu.add_command(
            label="复制", command=lambda: self.output.event_generate("<<Copy>>"))
        self.output_menu.add_command(label="全选", command=self._select_all)
        self.output_menu.add_separator()
        self.output_menu.add_command(label="清空输出", command=self.on_clear)
        self.output.bind("<Button-3>", self._popup_menu)

        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        tk.Label(self.root, textvariable=self.status_var, anchor="w",
                 relief="sunken").pack(fill="x", side="bottom")

    # ---------- 输出区 ----------
    def _append(self, text):
        """向只读输出区追加文本（内部临时恢复可写状态）"""
        self.output.config(state="normal")
        insert_ansi(self.output, text)
        self.output.see(tk.END)
        self.output.config(state="disabled")

    def _select_all(self):
        self.output.tag_add("sel", "1.0", tk.END)

    def _popup_menu(self, event):
        try:
            self.output_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.output_menu.grab_release()

    # ---------- 交互 ----------
    def choose_station(self, var, title):
        """弹出 省份→城市→站点 级联下拉框，确定后把选中的站名写回 var"""
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.transient(self.root)
        dlg.grab_set()

        frame = tk.Frame(dlg, padx=12, pady=10)
        frame.pack()

        prov_var = tk.StringVar()
        city_var = tk.StringVar()
        st_var = tk.StringVar()

        tk.Label(frame, text="省份：").grid(row=0, column=0, sticky="e", pady=3)
        prov_cb = ttk.Combobox(frame, textvariable=prov_var, state="readonly",
                               width=18, values=list(self.province_cities))
        prov_cb.grid(row=0, column=1, pady=3)

        tk.Label(frame, text="城市：").grid(row=1, column=0, sticky="e", pady=3)
        city_cb = ttk.Combobox(frame, textvariable=city_var, state="readonly",
                               width=18, values=[])
        city_cb.grid(row=1, column=1, pady=3)

        tk.Label(frame, text="站点：").grid(row=2, column=0, sticky="e", pady=3)
        st_cb = ttk.Combobox(frame, textvariable=st_var, state="readonly",
                             width=18, values=[])
        st_cb.grid(row=2, column=1, pady=3)

        def on_prov(_event=None):
            cities = self.province_cities.get(prov_var.get(), [])
            city_cb["values"] = cities
            city_var.set(cities[0] if cities else "")
            on_city()

        def on_city(_event=None):
            sts = self.city_stations.get(city_var.get(), [])
            st_cb["values"] = sts
            # 默认选中与城市同名的站（如"广州"），没有则选第一个
            st_var.set(next((s for s in sts if s == city_var.get()),
                            sts[0] if sts else ""))

        def on_ok(_event=None):
            if st_var.get():
                var.set(st_var.get())
            dlg.destroy()

        prov_cb.bind("<<ComboboxSelected>>", on_prov)
        city_cb.bind("<<ComboboxSelected>>", on_city)
        dlg.bind("<Escape>", lambda _e: dlg.destroy())
        dlg.bind("<Return>", on_ok)

        btns = tk.Frame(frame)
        btns.grid(row=3, column=0, columnspan=2, pady=(10, 0))
        tk.Button(btns, text="确定", width=8, command=on_ok).pack(side="left",
                                                                 padx=6)
        tk.Button(btns, text="取消", width=8,
                  command=dlg.destroy).pack(side="left", padx=6)

        on_prov()  # 初始化城市/站点列表

        # 居中显示在主窗口上
        dlg.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width()
                                       - dlg.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height()
                                       - dlg.winfo_height()) // 2
        dlg.geometry("+%d+%d" % (x, y))
        dlg.resizable(False, False)

    def on_gcd(self):
        if self.gcd_var.get():
            self.ktz_var.set(False)

    def on_ktz(self):
        if self.ktz_var.get():
            self.gcd_var.set(False)

    def get_date(self):
        """校验并返回 YYYY-MM-DD 格式日期，失败返回 None"""
        try:
            d = datetime.date(int(self.year_var.get()),
                              int(self.month_var.get()),
                              int(self.day_var.get()))
        except ValueError:
            messagebox.showwarning("提示", "日期无效，请重新选择（如 2 月没有 31 日）")
            return None
        return d.strftime("%Y-%m-%d")

    def get_seats(self):
        selected = [name for name in SEAT_OPTIONS if self.seat_vars[name].get()]
        return " ".join(selected) if selected else ALL_SEATS

    def get_inputs(self):
        """校验界面输入，返回 (fs, ts, date, seats) 或 None"""
        fs = self.fs_var.get().strip()
        ts = self.ts_var.get().strip()
        if not fs:
            messagebox.showwarning("提示", "请填写出发地")
            return None
        if not ts:
            messagebox.showwarning("提示", "请填写目的地")
            return None
        date = self.get_date()
        if not date:
            return None
        return fs, ts, date, self.get_seats()

    def build_query_kwargs(self, fs, ts, date, seats):
        kw = dict(
            from_station=fs,
            to_station=ts,
            date=date,
            seats=seats,
            trains_no=self.trains_var.get().strip(),
            zmode=self.z_var.get(),
            zzmode=self.zz_var.get(),
            remaining=self.r_var.get(),
            verbose=self.v_var.get(),
            gcd=self.gcd_var.get(),
            ktz=self.ktz_var.get(),
            proxies_file=None,
            stations_file=None,
            cdn_file=None,
        )
        if FROZEN:
            kw["stations_file"], kw["proxies_file"], kw["cdn_file"] = self.data_paths
        return kw

    def get_command(self, fs, ts, date, seats):
        return build_command(
            fs, ts, date, seats, self.trains_var.get().strip(),
            self.r_var.get(), self.gcd_var.get(), self.ktz_var.get(),
            self.v_var.get(), self.z_var.get(), self.zz_var.get())

    def on_copy_cmd(self):
        inputs = self.get_inputs()
        if not inputs:
            return
        fs, ts, date, seats = inputs
        cmdline = subprocess.list2cmdline(self.get_command(fs, ts, date, seats))
        self.root.clipboard_clear()
        self.root.clipboard_append(cmdline)
        self.status_var.set("命令已复制到剪贴板")

    def on_query(self):
        if self.running:
            messagebox.showinfo("提示", "正在查询中，请稍候…")
            return
        inputs = self.get_inputs()
        if not inputs:
            return
        fs, ts, date, seats = inputs
        self.save_config()
        self._append("$ " + subprocess.list2cmdline(
            self.get_command(fs, ts, date, seats)) + "\n\n")
        kwargs = self.build_query_kwargs(fs, ts, date, seats)
        self._start_worker(lambda: x12306.main.callback(**kwargs), "查询中…")

    def on_update_station(self):
        if self.running:
            messagebox.showinfo("提示", "有任务正在运行，请稍候…")
            return
        path = self.data_paths[0] if FROZEN else DEFAULT_STATIONS_FILE
        self._append(f"正在更新站点数据 → {path}\n\n")
        self._start_worker(lambda: update_station(path=path), "更新站点数据中…")

    def on_clear(self):
        self.output.config(state="normal")
        self.output.delete("1.0", tk.END)
        self.output.config(state="disabled")

    def on_stop(self):
        if self.running:
            self.suppress = True
            self._append("\n[已停止，正在结束后台任务…]\n")
            self.status_var.set("正在停止…")

    # ---------- 后台执行（进程内调用，exe 版和源码版通用） ----------
    def _start_worker(self, target, status):
        # 开启 ANSI 颜色输出（Windows 下默认关闭），poll_queue 会渲染成彩色文字
        os.environ["X12306_ANSI"] = "1"
        self.query_btn.config(state="disabled")
        self.status_var.set(status)
        self.running = True
        self.suppress = False
        threading.Thread(target=self._worker, args=(target,), daemon=True).start()

    def _worker(self, target):
        writer = QueueWriter(self.q)
        try:
            with contextlib.redirect_stdout(writer):
                target()
        except SystemExit as e:
            writer.write(f"\n[程序提前退出] {e}\n")
        except Exception:
            writer.write("\n[查询出错]\n" + traceback.format_exc() + "\n")
        finally:
            writer.finish()
            self.q.put(None)  # 结束标记

    def poll_queue(self):
        try:
            while True:
                item = self.q.get_nowait()
                if item is None:
                    self._finish()
                    continue
                if not self.suppress:
                    self._append(item)
        except queue.Empty:
            pass
        self.root.after(100, self.poll_queue)

    def _finish(self):
        self.running = False
        self.suppress = False
        self.query_btn.config(state="normal")
        self.status_var.set("完成")


def selftest():
    """打包自检：验证依赖、数据文件、真实查询，结果写入 selftest_result.txt"""
    lines = []
    try:
        st_file = (resolve_data_paths()[0] or DEFAULT_STATIONS_FILE)
        with open(st_file, "r", encoding="utf-8") as f:
            head = f.read(60).split("|")
        lines.append("stations file OK, first station: %s" % head[1])

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            x12306.main.callback(
                from_station="北京", to_station="上海", date="2026-08-31",
                seats="一等座 二等座", trains_no="",
                zmode=False, zzmode=False, remaining=True, verbose=False,
                gcd=False, ktz=False,
                proxies_file=None, stations_file=None, cdn_file=None,
            )
        out = buf.getvalue()
        lines.append("query output lines: %d" % len(out.splitlines()))
        lines.append("has result table: %s" % ("车次" in out))
        lines.append("---- first 600 chars ----")
        lines.append(out[:600])
        lines.append("SELFTEST OK")
    except BaseException:
        lines.append("SELFTEST FAILED")
        lines.append(traceback.format_exc())
    with open(os.path.join(BASE_DIR, "selftest_result.txt"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    try:
        root = tk.Tk()
        App(root)
        root.mainloop()
    except Exception:
        with open(ERROR_LOG, "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        try:
            messagebox.showerror("启动失败",
                                 "程序出错了，请把 gui_error.log 发给开发者。\n\n"
                                 + traceback.format_exc()[-800:])
        except Exception:
            pass


if __name__ == "__main__":
    main()
