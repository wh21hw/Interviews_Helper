from __future__ import annotations
import html
import re
from datetime import datetime
from difflib import SequenceMatcher

QUESTION_HINTS = (
    "什么", "为什么", "怎么", "如何", "怎样", "介绍", "解释", "区别", "比较", "推导",
    "手写", "代码", "设计", "实现", "复杂度", "原理", "优缺点", "场景", "指标", "损失",
    "是否", "哪些", "讲讲", "说说", "了解", "解决", "处理", "优化", "定义", "含义",
    "手撕", "原因", "能否", "有没有",
)

TOPICS = {
    "项目与实验": ("项目", "论文", "实验", "baseline", "基线", "消融", "复杂度"),
    "推荐链路": ("链路", "召回", "粗排", "精排", "排序", "重排", "看板"),
    "冷启动与迁移": ("冷启动", "新用户", "新商品", "新视频", "跨域", "迁移", "长尾"),
    "序列与注意力": ("序列", "din", "dien", "gru", "caser", "attention", "qkv", "transformer", "rankmixer"),
    "多任务学习": ("多任务", "mmoe", "ple", "esmm", "pcgrad", "损失权重", "梯度冲突"),
    "排序与特征交互": ("ctr", "deepfm", "wide&deep", "特征交叉", "排序模型", "rankmixer", "fm怎样", "fm时间"),
    "指标与实验": ("auc", "roc", "pr", "gauc", "uauc", "指标", "a/b", "ab实验", "评估", "样本比例"),
    "偏差与样本": ("偏差", "不平衡", "负样本", "正负样本", "采样", "有偏", "信息茧房"),
    "LLM与生成式推荐": ("大模型", "llm", "生成式", "sft", "ppo", "prompt", "多模态", "文案", "query"),
    "机器学习基础": ("梯度下降", "优化器", "过拟合", "逻辑回归", "交叉熵", "bce", "贝叶斯", "word2vec", "fm"),
    "深度学习训练": ("梯度消失", "梯度爆炸", "初始化", "激活函数", "学习率", "batch size", "batchsize", "归一化"),
    "编程与概率": ("代码", "手写", "数组", "矩阵", "二叉树", "概率", "top k", "全排列", "子集", "动态规划"),
    "计算机网络": ("tcp", "udp", "http", "https", "网络", "拥塞", "三次握手", "四次挥手", "dns"),
    "操作系统": ("进程", "线程", "协程", "死锁", "虚拟内存", "调度", "文件系统"),
    "数据库与缓存": ("mysql", "数据库", "事务", "索引", "redis", "缓存", "一致性", "隔离级别"),
    "系统设计": ("系统设计", "高并发", "分布式", "限流", "熔断", "消息队列", "微服务", "可用性"),
    "前端与客户端": ("javascript", "typescript", "react", "vue", "浏览器", "渲染", "android", "ios"),
    "语言与运行时": ("python", "java", "c++", "golang", "rust", "垃圾回收", "jvm", "并发"),
    "行为与协作": ("冲突", "协作", "压力", "规划", "职业", "离职", "优点", "缺点"),
}


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = value.replace("\u00a0", " ").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def normalize_question(value: str) -> str:
    value = value.lower()
    value = re.sub(r"^(一面|二面|三面|四面|加面|追问)[：:、\s-]*", "", value)
    value = re.sub(r"^[\d一二三四五六七八九十]+[.、)）:：\s-]+", "", value)
    value = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value)
    return value


def looks_like_question(line: str) -> bool:
    compact = normalize_question(line)
    if len(compact) < 5 or len(compact) > 130:
        return False
    noise = ("点赞", "收藏", "发布于", "登录", "关注", "反问环节", "反问：", "面试时间", "自我介绍",
             "基本情况", "面试官风格", "问题重合度", "复盘下来", "面试官人很好",
             "没想到", "最终是否拿offer", "不建议写在简历", "还在流程中", "总体比较轻松")
    if any(x in line for x in noise):
        return False
    numbered = bool(re.match(r"^[\d一二三四五六七八九十]+[.、)）:：]\s*", line))
    return numbered or line.rstrip().endswith(("?", "？")) or any(h.lower() in line.lower() for h in QUESTION_HINTS)


def extract_question_candidates(text: str) -> list[dict]:
    text = clean_text(text)
    text = re.sub(r"(?<!^)\s+(?=(?:\d{1,2}|[一二三四五六七八九十]+)[.、）):：]\s*)", "\n", text)
    found: list[dict] = []
    ocr_page: int | None = None
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = re.sub(r"^[\s>*#•·-]+", "", raw).strip()
        page_match = re.fullmatch(r"\[图片OCR 第(\d+)页\]", line)
        if page_match:
            ocr_page = int(page_match.group(1))
            continue
        line = re.sub(r"^(一面|二面|三面|四面|加面)[：:]\s*", r"\1：", line)
        if looks_like_question(line):
            question = re.sub(r"^[\d一二三四五六七八九十]+[.、)）]\s*", "", line)[:180]
            found.append({
                "question": question,
                "evidence": {
                    "type": "ocr" if ocr_page is not None else "text",
                    "page": ocr_page,
                    "line": line_number,
                    "excerpt": line[:240],
                },
            })
    return found


def split_questions(text: str) -> list[str]:
    return [item["question"] for item in extract_question_candidates(text)]


def topic_of(question: str) -> str:
    lower = question.lower()
    scores = {topic: sum(1 for word in words if word in lower) for topic, words in TOPICS.items()}
    topic, score = max(scores.items(), key=lambda item: item[1])
    return topic if score else "其他"


def infer_company(title: str, text: str) -> str:
    # 标题通常直接点名应聘公司，优先级高于正文；正文可能在复盘时提到多家公司。
    title_sample = re.sub(r"\s*[-—|]\s*小红书\s*$", "", title or "").lower()
    text_sample = (text or "")[:600].lower()
    names = {
        "字节跳动": ("字节", "抖音", "tiktok"),
        "阿里巴巴": ("阿里", "淘宝", "淘天", "阿里妈妈", "高德", "饿了么"),
        "腾讯": ("腾讯", "微信", "wxg", "pcg", "cdg", "ieg"),
        "美团": ("美团", "mtgr"), "快手": ("快手",), "百度": ("百度", "凤巢"),
        "京东": ("京东", "京东零售", "jdy"), "拼多多": ("拼多多", "pdd", "temu"),
        "滴滴": ("滴滴",), "小红书": ("小红书",), "网易": ("网易",),
        "华为": ("华为",), "小米": ("小米",), "携程": ("携程",),
        "哔哩哔哩": ("哔哩哔哩", "b站", "bilibili"), "Shopee": ("shopee",),
        "SHEIN": ("shein",), "蘑菇街": ("蘑菇街",), "蚂蚁集团": ("蚂蚁",),
    }
    for sample in (title_sample, text_sample):
        for company, keys in names.items():
            if any(k in sample for k in keys):
                return company
    return "其他/未知"


def infer_business(title: str, text: str) -> str:
    for sample in ((title or "").lower(), (text or "")[:500].lower()):
        if any(word in sample for word in ("广告", "ctr", "cvr", "ocpc", "ocpm", "pacing", "拍卖")):
            return "广告"
        if any(word in sample for word in ("搜索", "搜推", "query", "相关性", "learning to rank")):
            return "搜索"
        if any(word in sample for word in ("推荐", "召回", "精排", "粗排", "重排", "feed")):
            return "推荐"
        if any(word in sample for word in ("tts", "语音合成", "speech synthesis")):
            return "TTS"
    return "待识别"


def infer_date(text: str) -> str:
    """只提取含四位年份的明确日期，避免为 09-03 之类内容猜年份。"""
    for match in re.finditer(r"(?<!\d)(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})日?", text or ""):
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3))).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def deduplicate_questions(rows: list[dict], threshold: float = 0.84) -> list[dict]:
    output: list[dict] = []
    buckets: dict[str, list[int]] = {}
    for row in rows:
        norm = normalize_question(row["question"])
        if not norm:
            continue
        key = norm[:2]
        duplicate = None
        for idx in buckets.get(key, []):
            other = output[idx]["normalized"]
            if norm in other or other in norm or SequenceMatcher(None, norm, other).ratio() >= threshold:
                duplicate = output[idx]
                break
        if duplicate:
            source_ids = {source["source_id"] for source in duplicate["sources"]}
            if row["source"]["source_id"] not in source_ids:
                duplicate["sources"].append(row["source"])
            for field, value in (("companies", row["company"]), ("platforms", row["platform"]),
                                 ("businesses", row["business"]), ("confidence_levels", row["confidence"])):
                if value and value not in duplicate[field]:
                    duplicate[field].append(value)
            duplicate["frequency"] = len(duplicate["sources"])
            duplicate["independent_source_count"] = duplicate["frequency"]
            rank = {"A": 0, "B": 1, "C": 2}
            duplicate["confidence"] = min(duplicate["confidence_levels"], key=lambda x: rank.get(x, 9))
        else:
            item = {
                **row, "normalized": norm, "frequency": 1, "independent_source_count": 1,
                "sources": [row["source"]], "companies": [row["company"]],
                "platforms": [row["platform"]], "businesses": [row["business"]],
                "confidence_levels": [row["confidence"]],
            }
            output.append(item)
            buckets.setdefault(key, []).append(len(output) - 1)
    for item in output:
        item["companies"].sort()
        item["platforms"].sort()
        item["businesses"].sort()
        base = {"A": 0.90, "B": 0.72, "C": 0.52}.get(item["confidence"], 0.45)
        source_bonus = min(0.10, 0.03 * (item["frequency"] - 1))
        incomplete_penalty = 0.08 if all(not source.get("is_complete", True) for source in item["sources"]) else 0
        item["quality_score"] = round(max(0, min(1, base + source_bonus - incomplete_penalty)), 2)
    output.sort(key=lambda x: (-x["frequency"], x["topic"], x["question"]))
    return output
