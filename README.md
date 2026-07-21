# CH9347 Web Demo

## Release 构建与验证

`release/dashboard_bundle.html` 是 V7 基线；另外三个发布页面由 `scripts/build_release.py` 从基线内核和 `Demo/mocks/` UI 源生成。

```bash
python3 scripts/build_release.py
python3 scripts/validate_release.py
```

验证脚本会检查 HTML/JavaScript 语法、四个页面共享内核的 bytewise 一致性、本地资源、关键 UI 回归不变式及重复构建的确定性。需要本地安装 Python 3 和 Node.js。
