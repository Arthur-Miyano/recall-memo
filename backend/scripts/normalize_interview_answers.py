"""将 Python 与 Agent 题库改成自然、贴近工程实践的面试答案。"""

from __future__ import annotations

import sqlite3
import json
import re
from pathlib import Path


DATABASE = Path(__file__).resolve().parents[2] / "data" / "bagu.db"
PYTHON_SEED = DATABASE.parent / "questions" / "seed_python.json"
OLD_MARKER = "**展开说：**"


DIRECT_ANSWERS = {
    74: (
        "`with` 的作用是把“使用资源”和“释放资源”绑在一起。比如打开文件、"
        "拿数据库连接、加锁，正常执行完要释放；中途报错也一样要释放。"
        "用 `with` 就不用在每个分支里手动写清理逻辑。\n\n"
        "它的底层是上下文管理协议：进入 `with` 时会调用对象的 `__enter__()`，"
        "它的返回值可以通过 `as` 接收；离开代码块时，不管有没有异常，都会调用 "
        "`__exit__(exc_type, exc_val, exc_tb)` 做清理。`__exit__` 返回 `True` 时可以吞掉异常，"
        "不过业务代码里一般会谨慎使用。\n\n"
        "实际开发中，我最常用它管理文件、数据库事务和锁。核心价值不是语法本身，"
        "而是保证资源能被可靠释放，减少异常路径下的泄漏和遗忘。"
    ),
    176: (
        "我会把一个本地 Coding Agent 拆成六层，核心思路是：模型负责判断下一步，"
        "但真正的读代码、改代码、跑命令和交付结果，都要放在可控的工程流程里。\n\n"
        "第一层是交互层，负责接收用户、IDE 或 CLI 的请求，展示进度，并在高风险操作前发起确认。"
        "第二层是 Agent Runtime，也就是任务的大脑：它保存任务状态，做规划，挑选相关上下文，并决定用哪个模型。"
        "第三层是仓库与编码能力层，负责理解当前工作区、Git 改动和代码关系，再提供搜索、补丁编辑、终端、测试和 Git 等能力。"
        "第四层是安全执行层：命令要在工作区和权限范围内执行，联网、安装依赖、删除文件或部署这类操作需要额外审批。"
        "第五层是验证与交付层，修改后不能只看模型说“完成了”，还要跑目标测试、lint 或类型检查，检查 diff 有没有越界，再把验证结果和剩余风险告诉用户。"
        "第六层是存储、观测与恢复层，用来保存会话、计划、操作日志、trace、评测数据和任务快照；这样任务中断后可以继续，出了问题也能追溯。\n\n"
        "实际跑一次任务时，流程通常是：先读项目说明和 Git 状态，定位相关代码，列一个能验证的计划；"
        "接着做最小修改并运行针对性测试；测试失败就根据报错继续修，最后把改动、验证结果和风险交代清楚。"
        "这样做的重点不是让 Agent 自由发挥，而是让每一步都能检查、限制和恢复。"
    ),
    21: (
        "最左前缀说的是联合索引的使用规则。比如索引是 `(name, age, city)`，"
        "查询至少要能利用最左边的 `name`，才能按顺序继续利用后面的列；只查 `age` 或 `city`，"
        "通常用不上这棵联合索引。\n\n"
        "这里容易混淆两件事：`WHERE` 里条件写成 `age = ? AND name = ?`，还是 `name = ? AND age = ?`，"
        "一般不会影响优化器使用索引；真正重要的是查询条件是否覆盖了索引的左侧前缀。"
        "另外，遇到范围条件、函数运算或低选择性列时，后续列能否继续被有效利用也要看执行计划。\n\n"
        "实际优化时我不会只背规则，会用 `EXPLAIN` 看 `key`、`key_len` 和扫描行数，确认索引是否真的被用好。"
    ),
    31: (
        "`IN` 是判断某个值是否在一个集合里，`EXISTS` 是判断相关子查询是否至少能找到一行。"
        "两者表达的业务语义不同，但在 MySQL 这类数据库里，优化器常会把它们改写成半连接等执行方式，"
        "所以不能简单背成“子查询大就一定用 EXISTS”。\n\n"
        "写 SQL 时先选语义更清楚的写法：只是判断关联记录是否存在，用 `EXISTS` 很直观；"
        "需要匹配一个明确集合时，用 `IN` 更好读。再确认关联列有合适索引，并通过 `EXPLAIN` 看实际计划。"
    ),
    44: (
        "`redo log` 是 InnoDB 的重做日志，记录的是对数据页的物理修改。它的作用是："
        "数据库崩溃后，能把已经提交、但还没来得及刷回数据文件的修改重放出来，保证持久性。\n\n"
        "`undo log` 则保存旧版本信息，事务失败时可以回滚，也为 MVCC 的一致性读提供版本链。"
        "可以简单理解为：redo 负责“提交过的数据别丢”，undo 负责“改错了能撤回、读旧版本有依据”。"
    ),
    52: (
        "MySQL 和 Oracle 都是成熟的关系型数据库，不能简单说谁的性能一定更强；"
        "选型要看数据规模、并发模型、事务和高可用要求、团队经验以及许可证成本。\n\n"
        "MySQL 社区版开源、部署和运维相对轻量，常见于互联网业务；Oracle 是商业数据库，"
        "在大型企业场景中有完善的企业级能力和配套支持。SQL 细节也不同，例如 MySQL 常用 `LIMIT` 分页，"
        "Oracle 12c 以后支持 `OFFSET … FETCH`，旧写法常见 `ROWNUM`；MySQL 的自增列通常用 `AUTO_INCREMENT`，"
        "Oracle 可用 identity column 或 sequence。实际迁移时还要逐项验证函数、事务隔离、字符集和执行计划。"
    ),
    126: (
        "TLS 握手的目标是确认服务端身份，并协商出后续通信要用的对称会话密钥。"
        "面试里要先说明版本：TLS 1.2 和现在更常用的 TLS 1.3 流程并不一样。\n\n"
        "TLS 1.2 里，客户端发送 `ClientHello`，服务端返回 `ServerHello` 和证书；"
        "客户端验证证书后，常见做法是通过 ECDHE 协商共享密钥，再由双方派生会话密钥。"
        "TLS 1.3 把流程缩短为通常一次往返，并移除了 RSA 密钥交换，默认使用具备前向保密性的临时密钥交换。\n\n"
        "后续业务数据用对称加密传输，因为它更快；证书和非对称密码主要用来认证和安全协商。"
    ),
    128: (
        "GET 和 POST 最核心的区别是 HTTP 语义，不是“参数放哪里”或“谁更安全”。"
        "GET 表示安全读取，通常可被缓存；POST 通常表示向资源提交处理请求。参数可以分别放在 URL 或请求体，"
        "但这只是常见约定，不能据此判断安全性。\n\n"
        "幂等也取决于接口实现：规范上 GET、PUT、DELETE 应设计为幂等，POST 通常不保证幂等，"
        "但支付回调这类 POST 完全可以通过幂等键设计成重复调用也只生效一次。敏感数据无论用什么方法，"
        "都必须走 HTTPS，并避免把它放进会被日志和历史记录保存的 URL。"
    ),
    149: (
        "幂等是指同一个请求执行一次和执行多次，最终业务结果一样。它不是 HTTP 方法自动带来的属性，"
        "而是接口要主动设计出来的能力。\n\n"
        "例如创建订单或支付确认这类 POST 接口，客户端因超时重试时不能重复扣款。常见做法是让客户端带幂等键，"
        "服务端用唯一索引或 Redis 原子写入记录这个键；再配合业务状态机，已经完成的状态直接返回已有结果。"
        "分布式锁可以处理少数临界区，但不能替代持久化的去重和状态校验。"
    ),
    160: (
        "QLoRA 可以理解为“把基础模型用 4-bit 量化加载，再只训练 LoRA 适配器”。"
        "它比普通 LoRA 更省显存，因此适合在资源有限时做大模型微调。\n\n"
        "不过不能把它背成“24GB 显卡一定能微调 65B”。实际显存还取决于模型架构、上下文长度、batch size、"
        "优化器、是否做梯度检查点和训练框架。项目里应该先按目标配置压测，再决定模型大小和参数。"
    ),
}

OUTDATED_DATABASE_CONTEXT = "实际排查时，我会先看执行计划、数据量和访问路径，再决定是改 SQL、加索引还是调整数据模型。"

STACK_FIXES = {
    121: "network", 122: "network", 123: "network", 124: "network", 125: "network",
    126: "network", 127: "network", 128: "network", 129: "network", 130: "network",
    131: "network", 132: "os", 133: "os", 143: "distributed", 144: "distributed",
    145: "distributed", 146: "distributed", 147: "distributed", 149: "distributed", 152: "devops",
}

CONTEXT_SENTENCES = (
    "做服务端项目时，我会把它放到请求链路、阻塞风险、测试和线上部署里理解，而不是只背定义。",
    "先分清任务是 CPU 密集还是 I/O 密集，再决定用进程、线程还是协程；不要为了“并发”盲目上复杂方案。",
    "排查这类问题时，我会先确认变量是否指向同一个可变对象，再看修改的是对象本身还是变量绑定。",
    "工作里我更关注它会不会影响可读性、资源释放、排错和测试，而不只是记住底层名词。",
    "落地时先看召回的内容对不对，再调切分、检索和重排；模型回答得不好，很多时候根因不在模型。",
    "上线时模型只负责提出调用意图，参数校验、权限、超时、重试和审计必须由运行时兜底。",
    "实际会给信息加来源、时间和作用域，只把可复用的事实写入长期记忆，避免把模型猜测当事实。",
    "我会用可复现样例和自动校验衡量效果，不能只凭“这次回答看起来不错”来判断。",
    "实际做 Agent 时，重点是把模型能力放进可控的状态、工具和验证流程中，而不是让它自由发挥。",
    "实际排查时，我会先看执行计划、数据量和访问路径，再决定是改 SQL、加索引还是调整数据模型。",
    "前端开发里，我会优先保证状态来源清晰、组件边界稳定，再处理交互体验和性能细节。",
    "服务端代码里，我更关心接口边界、失败场景和可观测性，避免只在正常流程下看起来可用。",
    "做算法题时，我会先把数据规模和边界条件说清楚，再选择合适的数据结构和复杂度。",
    "这类基础知识最终要能帮助定位问题和做取舍，而不是只记住术语。",
    "排查 Redis 问题时，我会先确认命令模型、持久化配置、网络延迟和热点 Key，再决定怎么优化。",
    "排查网络问题时，我会先确认连接、超时、重试和链路日志，再判断问题是在客户端、网络还是服务端。",
    "排查并发或系统问题时，我会先确认资源边界和实际运行状态，再讨论线程、进程或 IPC 的取舍。",
    "在分布式场景里，我会优先明确消息是否允许重复、是否要求顺序，以及失败后如何恢复。",
    "部署时我更关注镜像是否可复现、配置是否外置，以及日志、健康检查和回滚是否可用。",
)

TERM_REPLACEMENTS = (
    ("Function Calling", "函数调用"),
    ("Tool Calling", "工具调用"),
    ("Prompt Injection", "提示词注入"),
    ("Multi-Agent", "多智能体"),
    ("Chain-of-Thought", "思维链"),
    ("Agent", "智能体"),
    ("Prompt", "提示词"),
    ("Token", "词元"),
    ("Embedding", "向量表示"),
    ("Chunking", "文本切分"),
    ("Memory", "记忆"),
    ("Runtime", "运行时"),
    ("Chatbot", "聊天机器人"),
)


def translate_terms(text: str) -> str:
    """中文化通用概念，但不改代码、命令或配置片段。"""
    text = text.replace("智能体ic", "智能体式").replace("智能体Executor", "AgentExecutor")
    parts = re.split(r"(`[^`]*`)", text)
    for index in range(0, len(parts), 2):
        for english, chinese in TERM_REPLACEMENTS:
            parts[index] = re.sub(rf"\b{re.escape(english)}\b", chinese, parts[index])
    return "".join(parts)


def clean_and_format(answer: str) -> str:
    """移除旧模板段，并把过长的说明自然分段。"""
    paragraphs = []
    for paragraph in original_answer(answer).replace("\r\n", "\n").split("\n\n"):
        paragraph = paragraph.strip().removeprefix("具体来说，").strip()
        if paragraph and paragraph not in CONTEXT_SENTENCES:
            paragraphs.append(paragraph)

    result = []
    for paragraph in paragraphs:
        if len(paragraph) <= 340:
            result.append(paragraph)
            continue
        sentences = re.split(r"(?<=[。！？；])", paragraph)
        chunk = ""
        for sentence in sentences:
            if chunk and len(chunk) + len(sentence) > 260:
                result.append(chunk)
                chunk = sentence
            else:
                chunk += sentence
        if chunk:
            result.append(chunk)
    formatted = "\n\n".join(result)
    if len(formatted) > 340 and "\n\n" not in formatted:
        formatted = formatted.replace("\n", "\n\n")
    return translate_terms(formatted)


def work_context(tech_stack: str, stem: str) -> str:
    """给每类知识点补上真实开发中的决策视角。"""
    if tech_stack == "python":
        if any(word in stem.lower() for word in ("fastapi", "django", "部署", "路由", "中间件")):
            return "做服务端项目时，我会把它放到请求链路、阻塞风险、测试和线上部署里理解，而不是只背定义。"
        if any(word in stem.lower() for word in ("gil", "线程", "进程", "协程", "event loop")):
            return "先分清任务是 CPU 密集还是 I/O 密集，再决定用进程、线程还是协程；不要为了“并发”盲目上复杂方案。"
        if any(word in stem.lower() for word in ("拷贝", "可变", "默认参数", "传递")):
            return "排查这类问题时，我会先确认变量是否指向同一个可变对象，再看修改的是对象本身还是变量绑定。"
        return "工作里我更关注它会不会影响可读性、资源释放、排错和测试，而不只是记住底层名词。"

    if tech_stack == "database":
        if "Redis" in stem:
            return "排查 Redis 问题时，我会先确认命令模型、持久化配置、网络延迟和热点 Key，再决定怎么优化。"
        return "实际排查时，我会先看执行计划、数据量和访问路径，再决定是改 SQL、加索引还是调整数据模型。"
    if tech_stack == "vue3":
        return "前端开发里，我会优先保证状态来源清晰、组件边界稳定，再处理交互体验和性能细节。"
    if tech_stack == "network":
        return "排查网络问题时，我会先确认连接、超时、重试和链路日志，再判断问题是在客户端、网络还是服务端。"
    if tech_stack == "os":
        return "排查并发或系统问题时，我会先确认资源边界和实际运行状态，再讨论线程、进程或 IPC 的取舍。"
    if tech_stack == "distributed":
        return "在分布式场景里，我会优先明确消息是否允许重复、是否要求顺序，以及失败后如何恢复。"
    if tech_stack == "devops":
        return "部署时我更关注镜像是否可复现、配置是否外置，以及日志、健康检查和回滚是否可用。"
    if tech_stack == "java":
        return "服务端代码里，我更关心接口边界、失败场景和可观测性，避免只在正常流程下看起来可用。"
    if tech_stack == "algorithm":
        return "做算法题时，我会先把数据规模和边界条件说清楚，再选择合适的数据结构和复杂度。"

    if any(word in stem.lower() for word in ("rag", "检索", "embedding", "chunk", "向量")):
        return "落地时先看召回的内容对不对，再调切分、检索和重排；模型回答得不好，很多时候根因不在模型。"
    if any(word in stem.lower() for word in ("工具", "function", "mcp", "高危", "调用")):
        return "上线时模型只负责提出调用意图，参数校验、权限、超时、重试和审计必须由运行时兜底。"
    if any(word in stem.lower() for word in ("记忆", "上下文", "context")):
        return "实际会给信息加来源、时间和作用域，只把可复用的事实写入长期记忆，避免把模型猜测当事实。"
    if any(word in stem.lower() for word in ("评测", "幻觉", "prompt", "json")):
        return "我会用可复现样例和自动校验衡量效果，不能只凭“这次回答看起来不错”来判断。"
    return "这类基础知识最终要能帮助定位问题和做取舍，而不是只记住术语。"


def original_answer(answer: str) -> str:
    """兼容第一轮格式，将原答案还原后再进行无模板改写。"""
    return answer.split(OLD_MARKER, 1)[-1].strip()


def rewrite(question_id: int | None, tech_stack: str, stem: str, answer: str) -> str:
    if (
        question_id in DIRECT_ANSWERS
        or stem == "with 语句的原理？"
        or "上下文管理器（with 语句）" in stem
    ):
        return clean_and_format(DIRECT_ANSWERS.get(question_id, DIRECT_ANSWERS[74]))

    return clean_and_format(answer)


def main() -> None:
    with sqlite3.connect(DATABASE) as connection:
        rows = connection.execute(
            "SELECT id, tech_stack, stem, answer FROM questions "
            "ORDER BY id"
        ).fetchall()
        updates = []
        stack_updates = []
        for question_id, tech_stack, stem, answer in rows:
            target_stack = STACK_FIXES.get(question_id, tech_stack)
            updated_answer = rewrite(question_id, target_stack, stem, answer)
            if question_id not in DIRECT_ANSWERS and (
                target_stack != tech_stack or "Redis" in stem
            ):
                updated_answer = updated_answer.replace(
                    OUTDATED_DATABASE_CONTEXT,
                    work_context(target_stack, stem),
                )
            if updated_answer != answer:
                updates.append((updated_answer, question_id))
            if target_stack != tech_stack:
                tags = json.loads(
                    connection.execute("SELECT tags FROM questions WHERE id = ?", (question_id,)).fetchone()[0]
                )
                if tags:
                    tags[0] = target_stack
                stack_updates.append((target_stack, json.dumps(tags, ensure_ascii=False), question_id))
        connection.executemany("UPDATE questions SET answer = ? WHERE id = ?", updates)
        connection.executemany(
            "UPDATE questions SET tech_stack = ?, tags = ? WHERE id = ?",
            stack_updates,
        )
    seed_questions = json.loads(PYTHON_SEED.read_text(encoding="utf-8"))
    seed_updates = 0
    for question in seed_questions:
        original = question["answer"]
        updated = rewrite(None, "python", question["stem"], original)
        if updated != original:
            question["answer"] = updated
            seed_updates += 1
    if seed_updates:
        PYTHON_SEED.write_text(
            json.dumps(seed_questions, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"已整理 {len(updates)} / {len(rows)} 道数据库题，并同步 {seed_updates} 道 Python 种子题。")


if __name__ == "__main__":
    main()
