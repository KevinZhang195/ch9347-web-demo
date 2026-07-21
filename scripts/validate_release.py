#!/usr/bin/env python3
"""
validate_release.py — 独立验证脚本，可在构建后或 CI 中运行。

检查：
  1. HTML 标签平衡（粗略）
  2. 内联 script 语法（node --check）
  3. 内核块在 4 个 release 页面间 bytewise 一致
  4. 必备 token 存在
  5. 三个新 UI 页面的回归不变式
  6. 本地 asset 引用可解析
  7. 构建确定性（重新生成不改变输出）
"""
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / "release"
BUILD_SCRIPT = ROOT / "scripts" / "build_release.py"

VOID_TAGS = {"area","base","br","col","embed","hr","img","input","link","meta","param","source","track","wbr"}

KERNEL_NAMES = ["legacy-probe","ch9347-lib","browser-support","data-manager","gp-driver","log-manager"]
COMMON_TOKENS = [
    "class DataManager", "class GPDriver", "T_0C100C_36_1023", "LogManager",
]
REDESIGNED_TOKENS = [
    "window.render = function", "window.__bindDataManager", 'id="soc-num"', 'id="logs-card"',
]
REGRESSION_IDS = ["bi-model", "bi-mfr", "bi-code"]
EXPECTED_RELEASE_NAMES = [
    "dashboard_bundle.html",
    "dashboard_ios_health.html",
    "dashboard_ev_app.html",
    "dashboard_smart_home.html",
]


class BalanceParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID_TAGS:
            self.stack.append((tag, self.getpos()[0]))

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1][0] == tag:
            self.stack.pop()
        else:
            self.errors.append((tag, self.getpos()[0], self.stack[-1] if self.stack else None))


def extract_kernel(text: str, name: str) -> str:
    start = f"<!-- KERNEL:{name} -->"
    end = f"<!-- /KERNEL:{name} -->"
    assert text.count(start) == 1, f"KERNEL start marker '{name}' not found or duplicated"
    assert text.count(end) == 1, f"KERNEL end marker '{name}' not found or duplicated"
    a = text.rfind("\n", 0, text.index(start)) + 1
    b = text.index(end, a) + len(end)
    return text[a:b]


def main() -> int:
    errors = []

    release_files = [RELEASE / name for name in EXPECTED_RELEASE_NAMES]
    missing = [path for path in release_files if not path.is_file()]
    if missing:
        for path in missing:
            errors.append(f"missing expected release file: {path.relative_to(ROOT)}")
        print(f"FAIL ({len(errors)} errors):")
        for error in errors:
            print(f"  ✗ {error}")
        return 1

    mock_files = sorted((ROOT / "Demo/mocks").glob("mock_*.html"))
    redesigned = release_files[1:]

    # ── 1. HTML 标签平衡 ──
    for path in release_files + mock_files:
        text = path.read_text(encoding="utf-8")
        parser = BalanceParser()
        parser.feed(text)
        if parser.errors or parser.stack:
            errors.append(f"{path.relative_to(ROOT)}: HTML imbalance errors={parser.errors} stack={parser.stack}")

    # ── 2. 内联 script 语法检查 ──
    for path in release_files + mock_files:
        text = path.read_text(encoding="utf-8")
        scripts = re.findall(r"<script(?:\s[^>]*)?>([\s\S]*?)</script>", text, re.I)
        for index, source in enumerate(scripts, 1):
            result = subprocess.run(["node", "--check", "-"], input=source, text=True, capture_output=True)
            if result.returncode != 0:
                errors.append(f"{path.relative_to(ROOT)} script {index}: {result.stderr}")

    # ── 3. 内核块 bytewise 一致 ──
    base_text = release_files[0].read_text(encoding="utf-8")
    for name in KERNEL_NAMES:
        ref = extract_kernel(base_text, name)
        for path in redesigned:
            cmp = extract_kernel(path.read_text(encoding="utf-8"), name)
            if cmp != ref:
                errors.append(f"{name} differs in {path.relative_to(ROOT)}")

    # ── 4. 必备 token ──
    for path in release_files:
        text = path.read_text(encoding="utf-8")
        for token in COMMON_TOKENS:
            if token not in text:
                errors.append(f"{path.relative_to(ROOT)} missing token: {token}")
    for path in redesigned:
        text = path.read_text(encoding="utf-8")
        for token in REDESIGNED_TOKENS:
            if token not in text:
                errors.append(f"{path.relative_to(ROOT)} missing token: {token}")

    # ── 5. 回归不变式 ──
    for path in redesigned:
        text = path.read_text(encoding="utf-8")
        assert 'id="bi-date"' not in text, f"{path.relative_to(ROOT)} has bi-date"
        for id_ in REGRESSION_IDS:
            if text.count(f'id="{id_}"') != 1:
                errors.append(f"{path.relative_to(ROOT)} missing or duplicate id={id_}")
        # 三列电池信息：无 bi-date 域
        logs_count = text.count("document.getElementById('logs-head').addEventListener")
        if logs_count != 1:
            errors.append(f"{path.relative_to(ROOT)} logs-head listener count {logs_count} != 1")
        if "window.addEventListener('pagehide'" not in text:
            errors.append(f"{path.relative_to(ROOT)} missing pagehide listener")
        if "if (!e.persisted) driver.stop();" not in text:
            errors.append(f"{path.relative_to(ROOT)} missing BFCache-safe driver cleanup")
        if "this._stopped = true" not in text:
            errors.append(f"{path.relative_to(ROOT)} missing GPDriver stopped guard")
        if "ecnt > maxRecords" not in text:
            errors.append(f"{path.relative_to(ROOT)} missing historical-record bounds check")
        if "var _renderTick = false;" not in text:
            errors.append(f"{path.relative_to(ROOT)} missing render batching")
        if "function esc(s)" not in text:
            errors.append(f"{path.relative_to(ROOT)} missing esc() helper")

    # ── 6. 本地 asset 引用 ──
    for path in release_files:
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r'(?:src|href)=["\']([^"\']+)["\']', text, re.I):
            ref = match.group(1)
            if ref.startswith(("data:", "http:", "https:", "#", "javascript:")):
                continue
            if not (path.parent / ref).resolve().exists():
                errors.append(f"{path.relative_to(ROOT)} missing asset: {ref}")

    # ── 7. 构建确定性 ──
    before = {p.name: p.read_bytes() for p in redesigned}
    subprocess.run([sys.executable, str(BUILD_SCRIPT)], cwd=ROOT, check=True, capture_output=True, text=True)
    after = {p.name: p.read_bytes() for p in redesigned}
    for name in before:
        if before[name] != after[name]:
            errors.append(f"deterministic rebuild changed {name}")

    # ── 报告 ──
    if errors:
        print(f"FAIL ({len(errors)} errors):")
        for e in errors:
            print(f"  ✗ {e}")
        return 1
    else:
        print("OK all checks passed")
        return 0


if __name__ == "__main__":
    sys.exit(main())