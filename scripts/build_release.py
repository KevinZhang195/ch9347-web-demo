#!/usr/bin/env python3
"""
build_release.py — 从 release/dashboard_bundle.html 提取内核，与 3 个 mock UI 合成 3 个新发布文件。

内核（数据+驱动+日志）保持字节一致；UI 完全用 mock 的 CSS/DOM/绘制层，事件桥接到 DataManager。
"""
import re
from pathlib import Path

ROOT = Path("/Volumes/Work/project/ch9347-web-demo")
BASE = (ROOT / "release/dashboard_bundle.html").read_text(encoding="utf-8").splitlines(keepends=False)

# ------- 定位内核 script 段 -------
# 行号（1-based, 与 grep 输出一致）：
#   707-714  : legacy-browser 探测
#   861-863  : CH9347Lib 混淆库
#   864-959  : polyfills + observeResize + BrowserSupport
#   960-1192 : DataManager
#   1193-1795: GPDriver 全体
#   2627-2703: LogManager
def slice_lines(a: int, b: int) -> str:
    return "\n".join(BASE[a-1:b])

legacy_probe = slice_lines(707, 714)
ch9347_lib   = slice_lines(861, 863)
browser_sup  = slice_lines(864, 959)
data_manager = slice_lines(960, 1192)
gp_driver    = slice_lines(1193, 1795)
log_manager  = slice_lines(2627, 2703)

# 校验：这几个必须存在的关键 token
for name, src, token in [
    ("legacy_probe", legacy_probe, "legacy-browser"),
    ("ch9347_lib",   ch9347_lib,   "_0x32c312"),
    ("browser_sup",  browser_sup,  "observeResize"),
    ("data_manager", data_manager, "class DataManager"),
    ("gp_driver",    gp_driver,    "class GPDriver"),
    ("gp_driver_nt", gp_driver,    "T_0C100C_36_1023"),
    ("log_manager",  log_manager,  "LogManager"),
]:
    assert token in src, f"[extract] {name} 缺少 token: {token}"

# ------- 3 个 mock 的 UI 提取 -------
def read_mock(path: Path):
    txt = path.read_text(encoding="utf-8")
    # 1. <style> ... </style>
    m = re.search(r"<style>([\s\S]*?)</style>", txt)
    assert m, f"{path.name}: 没找到 <style>"
    css = m.group(1)

    # 2. body 主体：从 <body> 后第一个 <div class="container"> 到 </div>（对应 container 的结束）
    m2 = re.search(r'<div class="container">([\s\S]*?)\n</div>\n\n<script>', txt)
    assert m2, f"{path.name}: 没找到 container 主体"
    body_inner = m2.group(1)

    # 3. mock JS（第 2 个 <script> 到最后一个 </script>）
    m3 = re.search(r"</style>\s*</head>[\s\S]*?<script>([\s\S]*?)</script>\s*</body>", txt)
    assert m3, f"{path.name}: 没找到主 JS"
    js = m3.group(1)

    return css, body_inner.strip(), js

MOCKS = ROOT / "Demo/mocks"
css_a, body_a, js_a = read_mock(MOCKS / "mock_A_ios_health.html")
css_b, body_b, js_b = read_mock(MOCKS / "mock_B_ev_app.html")
css_c, body_c, js_c = read_mock(MOCKS / "mock_C_smart_home.html")

# ------- 路径修正：mock 里 logo 路径是 ./../../release/assets/... （相对 Demo/mocks/）
#         写到 release/ 后要改成 ./assets/... （相对 release/）
def fix_asset_paths(body: str) -> str:
    return body.replace("./../../release/assets/", "./assets/")

body_a = fix_asset_paths(body_a)
body_b = fix_asset_paths(body_b)
body_c = fix_asset_paths(body_c)

# ------- 移除 mock 里的场景切换器（scenario-bar）+ 相关代码 -------
def strip_scenario_bar(body: str) -> str:
    # 移除 <div class="scenario-bar"> ... </div> 那一整块（它在 body_inner 之前，不在 container 里）
    return body  # container 内部无 scenario-bar；OK

def clean_mock_js(js: str) -> str:
    """
    - 去掉 scenario 定义与切换按钮监听
    - 保留 render(name) 函数（要重命名以避免冲突），并将其挂到 window
    - 由外部驱动改成事件驱动
    我们直接把 mock JS 整段作为"渲染器"，构造一个从 DataManager 快照生成 scn 对象的 adapter。
    """
    # 去掉：const scenarios = { ... };   （定义与场景数据）
    js = re.sub(r"const\s+scenarios\s*=\s*\{[\s\S]*?\};\s*", "", js, count=1)
    # 去掉：document.querySelectorAll('.scenario-bar button')... render('normal');
    js = re.sub(
        r"document\.querySelectorAll\('\.scenario-bar button'\)[\s\S]*?render\('normal'\);\s*$",
        "", js, count=1)
    return js.strip()

body_a = strip_scenario_bar(body_a)
body_b = strip_scenario_bar(body_b)
body_c = strip_scenario_bar(body_c)
js_a = clean_mock_js(js_a)
js_b = clean_mock_js(js_b)
js_c = clean_mock_js(js_c)

# 快速断言：mock 里必需的 DOM id（三个 mock 共有的字段）
REQUIRED_IDS = (
    "soc-num", "soh-num", "temp-num", "cycle-num",
    "v-pack", "i-pack", "p-pack",
    "cells-list", "cells-count", "abn-list",
    "log-count", "log-table-wrap",
    "logs-head", "logs-card",
    "bi-model", "bi-mfr", "bi-code",
    "product-badge",
)
for name, body in [("A", body_a), ("B", body_b), ("C", body_c)]:
    for id_ in REQUIRED_IDS:
        assert f'id="{id_}"' in body, f"[mock {name}] 缺少 id={id_}"

# ------- 事件桥（把 DataManager 事件转成 scn 快照并调用 render(...)） -------
BRIDGE_JS = r"""
/* ============================================================
   Bridge: 把 CH9347/BMS 数据流桥接到 UI render()
============================================================ */
(function () {
    'use strict';

    // UI 快照：默认未连接
    var state = {
        connected: false,
        productModel: '--',
        soc: 0, soh: 0, temp: 0,
        vPack: 0, iPack: 0, pPack: 0,
        cycle: 0,
        cells: [0],
        abnormals: { volt: null, chargeOT: null, dischargeOT: null },
        logs: [],
        battery: { model: '--', mfr: '--', date: '--', code: '--' }
    };
    // 电压异常 / 充电过温 / 放电过温 分别对应 abnormalRecord row = 0 / 1 / 2
    var abnormalKeys = ['volt', 'chargeOT', 'dischargeOT'];

    function fmtTime(dt) {
        if (!dt) return '';
        if (typeof dt === 'string') return dt;
        try {
            var d = new Date(dt);
            var pad = function (n) { return (n < 10 ? '0' : '') + n; };
            return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
                ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
        } catch (e) { return String(dt); }
    }

    function renderAll() {
        if (typeof window.render === 'function') {
            try { window.render(state); } catch (e) { console.error(e); }
        }
    }

    window.__bindDataManager = function (dm) {
        dm.addEventListener('connectedChanged', function (e) {
            state.connected = !!e.detail;
            renderAll();
        });
        dm.addEventListener('productModelChanged', function (e) {
            state.productModel = e.detail || '--';
            renderAll();
        });
        dm.addEventListener('batteryLevelChanged',  function (e) { state.soc = e.detail; renderAll(); });
        dm.addEventListener('batteryHealthChanged', function (e) { state.soh = e.detail; renderAll(); });
        dm.addEventListener('batteryTempChanged',   function (e) { state.temp = e.detail; renderAll(); });
        dm.addEventListener('totalVoltageChanged',  function (e) { state.vPack = e.detail; renderAll(); });
        dm.addEventListener('totalCurrentChanged',  function (e) { state.iPack = e.detail; renderAll(); });
        dm.addEventListener('totalPowerChanged',    function (e) { state.pPack = e.detail; renderAll(); });
        dm.addEventListener('cycleCountChanged',    function (e) { state.cycle = e.detail; renderAll(); });

        dm.addEventListener('cellCountChanged', function (e) {
            var n = e.detail;
            var next = [];
            for (var i = 0; i < n; i++) next.push(state.cells[i] || 0);
            state.cells = next;
            renderAll();
        });
        dm.addEventListener('cellVoltageChanged', function (e) {
            var d = e.detail;
            state.cells[d.index] = d.voltage;
            renderAll();
        });

        dm.addEventListener('abnormalRecordChanged', function (e) {
            var d = e.detail;
            var key = abnormalKeys[d.row];
            if (key) {
                state.abnormals[key] = { value: d.value, time: fmtTime(d.time) };
                renderAll();
            }
        });
        dm.addEventListener('abnormalRecordCleared', function (e) {
            var key = abnormalKeys[e.detail];
            if (key) {
                state.abnormals[key] = null;
                renderAll();
            }
        });

        dm.addEventListener('historicalLogsCleared', function () {
            state.logs = [];
            renderAll();
        });
        dm.addEventListener('historicalLogsUpdated', function (e) {
            var d = e.detail;
            state.logs.push({
                row: d.row,
                category: d.category,
                value: d.value,
                time: fmtTime(d.time)
            });
            // 页面渲染只显示最新 500 条，与 DataManager 上限一致
            if (state.logs.length > 500) state.logs.shift();
            renderAll();
        });

        dm.addEventListener('batteryModelChanged',   function (e) { state.battery.model = e.detail || '--'; renderAll(); });
        dm.addEventListener('manufacturerChanged',   function (e) { state.battery.mfr = e.detail || '--'; renderAll(); });
        dm.addEventListener('productionDateChanged', function (e) { state.battery.date = e.detail || '--'; renderAll(); });
        dm.addEventListener('batteryCodeChanged',    function (e) { state.battery.code = e.detail || '--'; renderAll(); });

        renderAll();
    };
})();
"""

# ------- 把每个 mock 的 `render(name)` 改造为 `window.render(scn)` -------
# 三个 mock 的 JS 结构都是：`function render(name){ const scn = scenarios[name]; ... }`
def mockjs_to_renderer(js: str) -> str:
    """
    将 mock 里 `function render(name){ const scn = scenarios[name]; ...}`
    改成 `window.render = function(scn){ ... };`
    """
    # 找到 function render(name){ 的开头
    m = re.search(r"function\s+render\s*\(\s*name\s*\)\s*\{\s*const\s+scn\s*=\s*scenarios\[name\];\s*", js)
    assert m, "mock JS 缺少 render(name) 模式"
    js = js[:m.start()] + "window.render = function (scn) {\n" + js[m.end():]
    # 找到与之匹配的最外层 } —— 用括号平衡
    start = js.find("window.render = function (scn) {")
    # 从 start 起找到匹配的花括号闭合
    i = js.find("{", start)
    depth = 0
    end = -1
    while i < len(js):
        ch = js[i]
        if ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0: end = i; break
        i += 1
    assert end != -1, "找不到 render 函数的收尾 }"
    # 在 } 之后加 ";"
    js = js[:end+1] + ";" + js[end+1:]
    return js

js_a = mockjs_to_renderer(js_a)
js_b = mockjs_to_renderer(js_b)
js_c = mockjs_to_renderer(js_c)

# ------- 组装 -------
DASH_TITLES = {
    "ios_health": "智能电源管理系统 - TRUSVOLT",
    "ev_app":     "智能电源管理系统 - TRUSVOLT",
    "smart_home": "智能电源管理系统 - TRUSVOLT",
}

def build(name: str, ui_css: str, ui_body: str, ui_js: str) -> str:
    title = DASH_TITLES[name]
    # 关键：compat-banner 与 log-panel + log-toggle 也要保留在页面里，让 LogManager 可用
    #    compat-banner 用 fixed 覆盖全屏，只有 BrowserSupport 检测失败时才 addClass 'visible'
    #    log-panel + log-toggle-btn 保留成侧栏，但初始隐藏；点击 toggle 才显示
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
{ui_css}

/* ----- 内嵌：兼容性 banner / 隐藏日志面板 ----- */
#compat-banner {{
    display: none;
    position: fixed; inset: 0; z-index: 9999;
    background: rgba(0,0,0,0.72); color: #fff;
    align-items: center; justify-content: center;
    padding: 40px 60px; text-align: center; font-size: 16px;
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
}}
#compat-banner.visible {{ display: flex; }}

#log-panel {{
    position: fixed; right: 12px; bottom: 60px; z-index: 200;
    width: 420px; max-height: 44vh; overflow: hidden;
    background: rgba(20,20,22,0.94); color: #cfd3dc;
    border-radius: 10px;
    font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 11px; line-height: 1.5;
    display: none; flex-direction: column;
    box-shadow: 0 8px 24px rgba(0,0,0,0.35);
}}
#log-panel.visible {{ display: flex; }}
#log-panel-header {{
    display: flex; align-items: center; justify-content: space-between;
    padding: 8px 12px; border-bottom: 1px solid rgba(255,255,255,0.08);
    font-size: 11px; color: #a3aab8; letter-spacing: 0.05em;
}}
#log-panel-header .btns {{ display: flex; gap: 6px; }}
#log-panel-header button {{
    border: 0; background: rgba(255,255,255,0.06); color: #cfd3dc;
    padding: 3px 10px; border-radius: 4px; cursor: pointer; font-size: 11px;
}}
#log-panel-header button:hover {{ background: rgba(255,255,255,0.12); }}
#log-entries {{ padding: 8px 12px; overflow: auto; flex: 1; }}
#log-entries .log-entry {{ white-space: pre-wrap; word-break: break-all; padding: 2px 0; border-bottom: 1px dashed rgba(255,255,255,0.05); }}
#log-entries .log-entry:last-child {{ border-bottom: 0; }}
#log-entries .log-time {{ color: #808591; margin-right: 6px; }}
#log-entries .log-entry.log-error {{ color: #ff8a8a; }}
#log-entries .log-entry.log-warn  {{ color: #ffcf7a; }}

#log-toggle-btn {{
    position: fixed; right: 12px; bottom: 12px; z-index: 201;
    width: 40px; height: 40px; border-radius: 50%;
    background: rgba(20,20,22,0.85); color: #cfd3dc;
    border: 0; cursor: pointer; font-size: 18px;
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 4px 12px rgba(0,0,0,0.25);
    opacity: 0.4; transition: opacity .2s;
}}
#log-toggle-btn:hover, #log-toggle-btn.active {{ opacity: 1; }}
    </style>
</head>
<body>
{legacy_probe}
    <div id="compat-banner"></div>

    <div class="container">
{ui_body}
    </div>

    <div id="log-panel">
        <div id="log-panel-header">
            <span>调试日志</span>
            <div class="btns">
                <button id="log-copy-btn">复制</button>
                <button id="log-clear-btn">清空</button>
            </div>
        </div>
        <div id="log-entries"></div>
    </div>
    <button id="log-toggle-btn" title="打开/关闭日志">≡</button>

    {ch9347_lib}
{browser_sup}
{data_manager}
{gp_driver}
    <script>
    /* ==== UI 渲染器（由 mock 转换而来） ==== */
{ui_js}
    </script>
{log_manager}
    <script>
{BRIDGE_JS}
    </script>
    <script>
    /* 主入口 */
    window.addEventListener('DOMContentLoaded', function () {{
        try {{ LogManager.init(); }} catch (e) {{ console.error('LogManager.init failed:', e); }}
        var logPanel = document.getElementById('log-panel');
        var logToggle = document.getElementById('log-toggle-btn');
        if (logToggle && logPanel) {{
            logToggle.addEventListener('click', function () {{
                var on = logPanel.classList.toggle('visible');
                logToggle.classList.toggle('active', on);
            }});
        }}

        var deviceBlockReason = BrowserSupport.getDeviceBlockReason();
        var dm = new DataManager();
        window.__bindDataManager(dm);

        if (deviceBlockReason) {{
            BrowserSupport.showBanner(deviceBlockReason);
            console.warn(deviceBlockReason);
        }} else {{
            var driver = new GPDriver(dm);
            driver.start();
        }}
    }});
    </script>
</body>
</html>
"""

out_a = build("ios_health", css_a, body_a, js_a)
out_b = build("ev_app",     css_b, body_b, js_b)
out_c = build("smart_home", css_c, body_c, js_c)

# ------- 断言 -------
for name, txt in [("A", out_a), ("B", out_b), ("C", out_c)]:
    for tok in ["class DataManager", "class GPDriver", "window.render = function", "window.__bindDataManager",
                "T_0C100C_36_1023", "LogManager", "id=\"soc-num\"", "id=\"logs-card\""]:
        assert tok in txt, f"[final {name}] missing token: {tok}"
    # 括号平衡（粗略）
    for pair in ["<html", "</html>"]:
        assert txt.count(pair) == 1, f"[final {name}] {pair} 数量不为 1"

RELEASE = ROOT / "release"
(RELEASE / "dashboard_ios_health.html").write_text(out_a, encoding="utf-8")
(RELEASE / "dashboard_ev_app.html").write_text(out_b, encoding="utf-8")
(RELEASE / "dashboard_smart_home.html").write_text(out_c, encoding="utf-8")

sizes = {p.name: p.stat().st_size for p in RELEASE.glob("dashboard_*.html")}
print("Wrote to release/:")
for k, v in sorted(sizes.items()):
    print(f"  {k:40s} {v/1024:7.1f} KB")
