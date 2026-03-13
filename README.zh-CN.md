# openclawskills

这是一个面向 OpenClaw 多虾协同架构的技能仓库。

英文版说明：

- [README.md](README.md)

## 这个仓库是干什么的

这个仓库保存的是一套可迁移、可复用的 OpenClaw 能力层，主要包括：

- `skills/`：可直接复用的技能
- `shared-awareness/`：共享认知文件
- `workspace-seeds/`：工作区种子文件

它对应的是一套分工明确的龙虾团队架构：

- `main`：主管虾，负责调度
- `info`：信息虾，负责外部即时检索
- `knowledge`：知识库虾，负责长期记忆
- `writer`：图文虾，负责内容生产
- `rescue`：运维虾，负责巡检与恢复

## 命名规则

所有以 `BLY-` 开头的技能，都是这套体系里的自建技能。

例如：

- `BLY-info-search-planner`
- `BLY-info-search-executor`
- `BLY-info-source-verifier`
- `BLY-info-news-verifier`
- `BLY-info-evidence-pack`

这样做的目的很简单：

- 一眼区分哪些是自己的技能
- 一眼区分哪些是外部借鉴或改造的技能

## 当前包含的技能

### 信息检索层

- `BLY-info-search-planner`
  - 把模糊问题拆成结构化检索计划
- `BLY-info-search-executor`
  - 执行真实检索，默认优先 `web_search`
- `BLY-info-source-verifier`
  - 判断来源是否可靠、是否够资格支撑结论
- `BLY-info-news-verifier`
  - 专门处理“最近 / 最新 / 今天 / 当前”这类时效型问题
- `BLY-info-evidence-pack`
  - 把可用证据整理成标准交付包
- `gold-rmb-realtime`
  - 金价与汇率相关即时查询
- `x-monitor`
  - X 账号监控
- `wechat-official-monitor`
  - 公众号监控能力，当前更适合手工启用

### 知识库层

- `wechat-article-capture`
  - 文章抓取与入库
- `article-knowledge-manager`
  - 文章级知识检索与管理
- `knowledge-base-manager`
  - 知识库维护与长期记忆支持

### 写作与交付层

- `general-material-pack`
  - 通用素材包与短文成稿
- `feishu-cloud-doc`
  - 飞书云文档创建与更新
- `runninghub-image`
  - 生图能力，供图文虾调用

### 运维层

- `lobster-supervisor`
  - 服务、timer、端口、健康检查与恢复辅助

### 公共层

- `common/`
  - 多个技能共享的辅助脚本

## 仓库结构

```text
openclawskills/
├─ skills/
│  ├─ BLY-info-search-planner/
│  ├─ BLY-info-search-executor/
│  ├─ BLY-info-source-verifier/
│  ├─ BLY-info-news-verifier/
│  ├─ BLY-info-evidence-pack/
│  ├─ general-material-pack/
│  ├─ feishu-cloud-doc/
│  ├─ runninghub-image/
│  ├─ article-knowledge-manager/
│  ├─ knowledge-base-manager/
│  ├─ wechat-article-capture/
│  ├─ gold-rmb-realtime/
│  ├─ x-monitor/
│  ├─ lobster-supervisor/
│  └─ common/
├─ shared-awareness/
└─ workspace-seeds/
```

## 推荐架构

### 角色分工

- `main`：只调度，不自己承载具体业务
- `info`：只检索，不入库
- `knowledge`：只做记忆层、档案层、知识库层
- `writer`：只做内容生产与交付
- `rescue`：只做运维与自愈

### `info` 推荐检索链路

对开放网络检索，推荐固定走这条链：

1. `BLY-info-search-planner`
2. `BLY-info-search-executor`
3. `BLY-info-source-verifier`
4. `BLY-info-news-verifier`（仅时效型问题）
5. `BLY-info-evidence-pack`

### 推荐执行原则

- 默认优先 `web_search`
- 用 `web_fetch` 深读候选页面
- DDG 只做兜底
- 默认不使用国内通用搜索引擎
- 优先官网、官方文档、官方仓库、官方公告、可信国际媒体
- 证据不足时，明确说不足，不要硬编

## 在新机器上怎么用

### 方式一：克隆整个仓库

```bash
git clone https://github.com/buliyang0407/openclawskills.git
```

然后把需要的技能拷贝到 OpenClaw 工作区：

```bash
mkdir -p /path/to/openclaw/workspace/skills
cp -r openclawskills/skills/BLY-info-search-planner /path/to/openclaw/workspace/skills/
cp -r openclawskills/skills/BLY-info-search-executor /path/to/openclaw/workspace/skills/
cp -r openclawskills/skills/BLY-info-source-verifier /path/to/openclaw/workspace/skills/
cp -r openclawskills/skills/BLY-info-news-verifier /path/to/openclaw/workspace/skills/
cp -r openclawskills/skills/BLY-info-evidence-pack /path/to/openclaw/workspace/skills/
```

### 方式二：只取需要的 skill

例如只装一个：

```bash
mkdir -p /path/to/openclaw/workspace/skills/BLY-info-search-planner
cp -r skills/BLY-info-search-planner/* /path/to/openclaw/workspace/skills/BLY-info-search-planner/
```

## 哪些内容会放进仓库，哪些不会

仓库中会保留：

- `SKILL.md`
- `scripts/`
- `templates/`
- `references/`
- `workspace-seeds/`
- `shared-awareness/`

仓库中不会保留：

- `/etc/openclaw/*.env`
- token、app secret、私钥
- 生产环境里的目标 ID
- 运行中的状态数据

## 自测

部分自建技能带有轻量自测。

例如：

```bash
python skills/BLY-info-suite-selftest.py
```

这会检查：

- frontmatter 名称是否一致
- 是否包含 workflow / output section
- 是否带模板
- 是否至少有 3 条 eval

## 这个仓库接下来适合怎么发展

- 继续往里加 `BLY-*` 自建技能
- 让技能小而清晰，而不是堆成一个超级大 skill
- 把生产 secrets 永远留在仓库外
- 把这套多虾架构做成可以迁移到新机器的能力层

## 为什么要做这个仓库

目标很直接：

- 把真实生产环境里有价值的能力沉淀下来
- 让未来换机器、换服务器、换环境时更容易迁移
- 让这套“龙虾团队”分工体系更清楚、更可复用

如果这些内容对你有帮助，欢迎点个 star。
