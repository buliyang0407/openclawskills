# openclawskills

这是一个给 OpenClaw 使用的个人技能仓库，目前包含两套技能：

- `gold-rmb-realtime`
- `x-monitor`

## 技能说明

### 1. `gold-rmb-realtime`

用途：

- 查询实时人民币金价
- 输出 `人民币元/盎司`
- 输出 `人民币元/克`
- 支持固定时间播报
- 支持阈值提醒

当前设计重点：

- 固定播报时间是 `08:00` 和 `20:00`
- 不应被理解成“每小时播报”
- 使用 `openclaw message send` 发消息，方便切换到飞书等渠道

依赖：

- `python3`
- `systemctl`
- `openclaw`
- `/etc/openclaw/gold-rmb.env`

环境变量示例：

```env
TWELVEDATA_API_KEY=your_key
DELIVERY_CHANNEL=feishu
DELIVERY_TARGET=ou_xxx
MOVE_THRESHOLD_CNY_PER_GRAM=50.00
MIN_PUSH_INTERVAL_SECONDS=43200
```

### 2. `x-monitor`

用途：

- 监控指定 X.com 账号的新帖子
- 支持新增、删除、查看、预览监控账号
- 支持中英双语通知
- 能区分原创、回复、引用、转发
- 对引用和转发，会尽量把原帖内容一起带上

当前设计重点：

- 默认每小时轮询一次
- 每个账号每次只拉最近少量帖子，控制 API 消耗
- 新增账号时只从“当前最新帖”开始，不会把历史帖子一次性灌出来

依赖：

- `python3`
- `systemctl`
- `openclaw`
- `/etc/openclaw/x-monitor.env`

环境变量示例：

```env
SOCIALDATA_API_KEY=your_key
DELIVERY_CHANNEL=feishu
DELIVERY_TARGET=ou_xxx
POLL_LIMIT=5
TRANSLATE_ENABLED=true
```

## 如何安装到 OpenClaw

下面假设你的 OpenClaw 工作目录在：

```bash
/root/.openclaw/workspace
```

### 方式一：直接克隆整个仓库

```bash
cd /root/.openclaw/workspace
git clone https://github.com/buliyang0407/openclawskills.git
```

然后把具体技能拷贝到 OpenClaw 的 `skills` 目录：

```bash
mkdir -p /root/.openclaw/workspace/skills
cp -r /root/.openclaw/workspace/openclawskills/skills/gold-rmb-realtime /root/.openclaw/workspace/skills/
cp -r /root/.openclaw/workspace/openclawskills/skills/x-monitor /root/.openclaw/workspace/skills/
```

### 方式二：只拷贝某一个技能

例如只装 `x-monitor`：

```bash
mkdir -p /root/.openclaw/workspace/skills/x-monitor
cp -r skills/x-monitor/* /root/.openclaw/workspace/skills/x-monitor/
```

## 安装后怎么验证

### 验证 skill 是否被 OpenClaw 识别

```bash
openclaw skills info gold-rmb-realtime
openclaw skills info x-monitor
```

### 验证金价 skill

```bash
python3 /root/.openclaw/workspace/skills/gold-rmb-realtime/scripts/gold_rmb_quote.py --show-status
```

### 验证 X 监控 skill

```bash
python3 /root/.openclaw/workspace/skills/x-monitor/scripts/x_monitor.py --show-status
python3 /root/.openclaw/workspace/skills/x-monitor/scripts/x_monitor.py --preview-account @elonmusk --limit 3
```

## 重要注意事项

1. 不要把 `/etc/openclaw/*.env` 上传到 GitHub。
2. 不要把任何 API key、飞书目标 ID、服务器私钥一起提交。
3. 技能仓库只保存：
   - `SKILL.md`
   - `scripts/`
   - `references/`
4. 运行时配置应该单独放在服务器上。

## 建议的目录结构

```text
skills/
├─ gold-rmb-realtime/
│  ├─ SKILL.md
│  └─ scripts/
│     └─ gold_rmb_quote.py
└─ x-monitor/
   ├─ SKILL.md
   ├─ scripts/
   │  └─ x_monitor.py
   └─ references/
      └─ api_notes.md
```
