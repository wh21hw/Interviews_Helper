# 架构设计

## 目标

项目的核心是让 Agent 根据任意目标岗位生成可以追溯、可以重建、可以人工复核的个人面试问题库。每一道规范题都必须能够回到原始来源、正文行号或 OCR 页码。

## 推荐的数据流水线

```text
关键词与 URL
    ↓
平台适配器（发现、详情、登录状态检测）
    ↓
原始快照（只追加，立即落盘）
    ↓
正文与图片 OCR
    ↓
候选题抽取
    ↓
相关性、规范化与语义去重
    ↓
证据校验与质量评分
    ↓
SQLite / JSON / HTML
```

浏览器层只负责获取用户正常可见的内容。它不决定题目含义，也不直接修改规范题库。处理层只读取已经落盘的快照，因此解析规则或模型升级后可以离线重建，无需重新访问平台。

## 模块边界

当前代码按以下边界组织：

```text
src/interviews_helper/
  cli.py                 命令行入口
  models.py              Post、Question、Evidence、Run 等数据模型
  config.py              配置加载与校验
  browser.py             Chrome/CDP 生命周期与 Profile 管理
  platforms/
    xiaohongshu.py        搜索、详情和多图读取
    public.py             牛客、知乎、公众号与普通网页正文读取
  pipeline/
    questions.py         候选题抽取、规范化、分类与去重
  storage/
    repository.py        原始快照与规范 SQLite
    checkpoint.py        原子运行状态与断点续跑
  report/
    builder.py           静态报告生成
  retrieval.py           grep 与本地向量混合召回
```

平台差异应封装在适配器中。新增平台只实现发现、详情读取和阻断检测，不改动去重、存储与报告代码。

## Agent 应放在哪里

Agent 只作为可选的处理节点，不能控制账号和访问频率，也不能绕过平台验证。

适合 Agent 的任务：

- 判断来源是否真的是面经，识别课程推广、招聘广告和纯教程；
- 把口语、OCR 断句和错别字改成专业且不改变原意的问题；
- 将一道复合题拆成若干原子问题，并保留共同证据；
- 按目标岗位的知识体系打多标签，补充公司、岗位和业务方向候选；
- 对规则去重后的候选对做语义复核；
- 标记证据不足、无法从原文支持的题目，交给人工处理。

不适合 Agent 的任务：

- 登录、验证码处理、Cookie 管理和浏览器 Profile 管理；
- 请求调度、限速、重试和断点恢复；
- 原始正文、图片顺序和来源 URL 的保存；
- SQLite 主键、数据迁移和发布构建；
- 在没有原文证据时补写所谓“面试原题”。

初期采用单个结构化整理节点即可。输入为一篇来源及其证据行，输出必须符合固定 JSON Schema，并记录模型、提示词版本和原始输出。只有当“发现新来源”和“内容复核”需要独立扩展时，再拆成 Scout 与 Curator；无需为了形式引入多 Agent。

## 可复现性

任何模型处理结果都应带以下字段：

- `model_provider`、`model_name`；
- `prompt_version`、`schema_version`；
- `source_id` 与证据位置；
- `created_at`；
- `decision`、`confidence` 与 `review_status`；
- 输入正文的内容哈希。

模型不可用时，规则流水线仍应能完成采集、抽题、去重和报告生成。Agent 是增强项，不是运行项目的前置条件。
