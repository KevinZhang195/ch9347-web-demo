# ch9347-web-demo 样式修改说明书

## 任务概述

将 `Demo/index.html` 从当前浅色主题（金色顶部栏 + 浅灰背景 + 白色卡片）改造为**深色主题**（黑色背景 + 科技感卡片 + 仪表盘/图标样式），匹配提供的效果图。

---

## 第一步：备份

已将 `Demo/index.html` 备份为 `Demo/index_backup.html`

---

## 第二步：CSS 深色主题改造

### 2.1 修改 `:root` 变量

找到 CSS 顶部的 `:root` 块并替换为：

```css
:root {
    --bg-dark: #0A0E1A;
    --card-bg: #141A2E;
    --card-border: rgba(0, 180, 255, 0.15);
    --card-shadow: 0 4px 30px rgba(0, 0, 0, 0.5);
    --accent-blue: #00B4FF;
    --accent-cyan: #00E5FF;
    --accent-green: #00E676;
    --accent-orange: #FF9800;
    --accent-red: #FF5252;
    --text-primary: #FFFFFF;
    --text-secondary: rgba(255, 255, 255, 0.7);
    --text-dim: rgba(255, 255, 255, 0.4);
    --glow-blue: 0 0 20px rgba(0, 180, 255, 0.3);
    --glow-green: 0 0 20px rgba(0, 230, 118, 0.3);
    --header-gradient: linear-gradient(135deg, #0A0E1A 0%, #141A2E 50%, #0A0E1A 100%);
}
```

### 2.2 修改 `body` 基础样式

替换 `html, body` 块，改 background 为 `var(--bg-dark)`

### 2.3 顶部栏改造

替换 `#top-bar`，改为深色 `var(--header-gradient)` 背景 + 底部 `1px solid var(--card-border)`

### 2.4 内容区改造

替换 `#content-area`，改为 `background: var(--bg-dark)`

### 2.5 卡片样式改造（最关键）

所有 `.widget-card` 改为暗色科技感卡片：

```css
.widget-card {
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 16px;
    padding: 16px 20px;
    box-shadow: var(--card-shadow);
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    position: relative;
    overflow: hidden;
}

/* 卡片上方光晕装饰线 */
.widget-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 20%;
    right: 20%;
    height: 1px;
    background: linear-gradient(90deg, transparent, var(--accent-blue), transparent);
    opacity: 0.6;
}
```

`.card-title` → 字体 13px，颜色 `var(--text-secondary)`，间距

### 2.6 底部信息栏

`#bottom-bar` 和 `#battery-info` 改为深色风格

---

## 第三步：Canvas 绘制函数重写

### 3.1 电池健康度环（`drawHealthGauge`）

圆形弧线，从 225° 到 315°，`lineWidth: 8`, `lineCap: round`
- 背景弧：`rgba(255,255,255,0.05)`
- 进度弧：渐变 `#00E5FF → #00E676`
- 中心：大号白色数字 + 小号 `%` 文本

### 3.2 电池图标（`drawBattery`）

矩形电池轮廓 + 顶部小帽 + 内部填充色
- 绿色 >20%，橙色 <20%，红色 <10%
- 下方显示 `67%` 数字

### 3.3 循环次数

当前已有 `cycle-value` 和 `cycle-unit`，只需更新颜色：
- 数字：白色，`clamp(28px, 4vw, 42px)` 字体
- 单位：`var(--text-secondary)`，下方显示"累计循环"小标签

### 3.4 温度

当前已有 `temp-value`，更新颜色逻辑：
- `font-size: clamp(24px, 3.5vw, 38px)`
- 颜色条件：`≤45°C` → `#00E676`, `45-60°C` → `#FF9800`, `>60°C` → `#FF5252`

### 3.5 仪表盘（`drawGauge`）

半圆弧（车速表样式）：
- 从 `Math.PI * 1.1` 到 `Math.PI * 2.9`
- 背景弧：半透明
- 进度弧：蓝→绿→橙 渐变色
- 中心：大号数值 + 小号单位
- 三表范围：电压 0-16V，电流 0-5A，功率 0-40W

### 3.6 电芯电压条形图（`drawCellVoltages`）

四条水平条形 + 标签 + 电压值：
- `CELL 1` ~ `CELL 4` 左对齐标签
- 彩色条形（绿色/黄色/橙色基于电压值）
- 右侧白色 `XX.XXV` 数值

### 3.7 异常记录

- 表头行：时间 | 异常类别 | 异常数值
- 数据行分隔线：`rgba(255,255,255,0.05)`
- 异常类别颜色区分

---

## 第四步：不要改动的部分

1. **混淆的 `_0x...` JavaScript 块**（页面底部约 300+ 行） — 完全不动！
2. **base64 图片数据**（`logo-area` 中的 data:image 字符串） — 不动
3. **HTML 元素结构和 id/class 命名** — 不动
4. **HTML 中的事件绑定（onerror 等）** — 不动
5. **HTML 中 data 属性（如数据值名称）** — 不动

---

## 执行命令

完成修改后，执行：

```bash
cd /Volumes/Work/project/ch9347-web-demo
git add -A
git commit -m "style: 改造为深色科技感主题，匹配效果图
- CSS 从浅色改为黑色深色主题
- Canvas 仪表盘改为半圆弧车速表样式
- 电池健康度改用圆形进度环
- 电量改用电池图标 + 百分比
- 电芯电压改用水平条形图
- 卡片增加光晕装饰线"
```

---

## 设计参考

- **主色调**：深蓝黑 `#0A0E1A` 背景，藏青 `#141A2E` 卡片
- **强调色**：`#00B4FF` 蓝色，`#00E5FF` 青色
- **语义色**：绿 `#00E676`（健康/正常），橙 `#FF9800`（警告），红 `#FF5252`（危险）
- **字体**：白色 + 灰色透明度文字层级
- **光效**：卡片顶部蓝色光晕线，卡片外发光阴影
