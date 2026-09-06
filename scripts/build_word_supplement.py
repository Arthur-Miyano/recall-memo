"""Build the tech-word supplement table in data/ecdict.db.

ECDICT (stardict.csv) is a general learner's dictionary and lacks the
framework names, coined terms and Python identifiers that fill the
question bank. This script adds a small hand-curated `supplement` table
covering exactly the words the bank uses but ECDICT misses. The backend
words API falls back to this table after a direct ECDICT miss.

Run:  backend/.venv/Scripts/python.exe scripts/build_word_supplement.py
"""
import os
import sqlite3
import sys

# word -> (phonetic, translation). Phonetic may be "" for acronyms that
# are spelled out letter by letter when spoken.
ENTRIES = {
    # ---- 高频：数据库 / 存储 ----
    "innodb": ("ˈɪnəʊ diː biː", "MySQL 默认存储引擎，支持事务、行级锁和 MVCC"),
    "mvcc": ("", "Multi-Version Concurrency Control，多版本并发控制，读作 M-V-C-C"),
    "binlog": ("ˈbɪnlɒɡ", "MySQL 二进制日志，用于主从复制和数据恢复"),
    "readview": ("riːd vjuː", "InnoDB MVCC 的一致性读视图（Read View）"),
    "next-key": ("nekst kiː", "next-key lock：InnoDB 行锁 + 间隙锁的组合，防幻读"),
    "redis": ("ˈredɪs", "Remote Dictionary Server，内存键值数据库"),
    "rabbitmq": ("ˈræbɪt em kjuː", "开源消息队列，基于 AMQP 协议"),
    "rocketmq": ("ˈrɒkɪt em kjuː", "阿里开源的分布式消息队列"),
    "mongodb": ("ˌmɒŋɡəʊ diː biː", "文档型 NoSQL 数据库"),
    "postgresql": ("ˌpəʊstɡres kjuː el", "开源关系型数据库，口语里直接说 Postgres"),
    "myisam": ("maɪˈeɪsəm", "MySQL 老式存储引擎，不支持事务和行级锁"),
    "tinyint": ("ˈtaɪni ɪnt", "MySQL 微整型，占 1 字节"),
    "bigint": ("bɪɡ ɪnt", "MySQL 大整型，占 8 字节"),
    "filesort": ("faɪl sɔːt", "MySQL 无法利用索引时的额外排序操作"),
    "setnx": ("", "Redis 命令：key 不存在才写入（SET if Not eXists），分布式锁的基础，读作 set-N-X"),
    "redlock": ("red lɒk", "Redis 官方多节点分布式锁算法"),
    "everysec": ("", "Redis AOF 刷盘策略：每秒刷一次"),
    "bgrewriteaof": ("", "Redis 后台重写 AOF 文件的命令/配置"),
    "mysqlbinlog": ("", "MySQL 自带的 binlog 解析工具"),
    "processlist": ("ˈprəʊses lɪst", "MySQL 当前连接/线程列表（SHOW PROCESSLIST）"),
    "infile": ("", "LOAD DATA INFILE：MySQL 批量导入文件的语法"),
    "rewritebatchedstatements": ("", "MySQL JDBC 参数：重写批量 SQL 提升写入性能"),
    "jsonb": ("", "PostgreSQL 的二进制 JSON 类型，支持索引"),
    "bson": ("ˈbiːsən", "MongoDB 使用的二进制 JSON 格式"),
    "mycat": ("maɪ kæt", "国产 MySQL 分库分表中间件"),
    "shardingsphere": ("ʃɑːdɪŋ sfiːə", "Apache 旗下的分库分表中间件"),
    "mybatis-plus": ("maɪˈbætɪs plʌs", "MyBatis 的增强 ORM 框架"),
    "redisson": ("ˈredɪsən", "Redis 的 Java 客户端，封装了分布式锁等高级功能"),
    "qdrant": ("ˈkwɒdrənt", "Rust 写的向量数据库"),
    "pgvector": ("piː dʒiː ˈvektə", "PostgreSQL 的向量检索扩展"),
    "elasticsearch": ("ɪˈlæstɪk sɜːtʃ", "分布式搜索与分析引擎"),

    # ---- 高频：大模型 / Agent ----
    "langchain": ("læŋ tʃeɪn", "大模型应用开发框架"),
    "langgraph": ("læŋ ɡrɑːf", "LangChain 团队出品的 Agent 状态图编排框架"),
    "langsmith": ("læŋ smɪθ", "LangChain 的观测与调试平台"),
    "lcel": ("", "LangChain Expression Language，LangChain 表达式语言，读作 L-C-E-L"),
    "agentexecutor": ("ˈeɪdʒənt ɪɡˈzekjətə", "LangChain 的 Agent 执行器"),
    "stategraph": ("steɪt ɡrɑːf", "LangGraph 里的状态图对象"),
    "astream": ("eɪ striːm", "LangChain 的异步流式输出接口"),
    "recursivecharactertextsplitter": ("", "LangChain 的递归字符文本切分器"),
    "agentic": ("eɪˈdʒentɪk", "智能体化的，如 agentic workflow（智能体工作流）"),
    "tokenizer": ("ˈtəʊkənaɪzə", "分词器，把文本切成 token"),
    "tokenization": ("ˌtəʊkənaɪˈzeɪʃn", "分词（把文本切成 token 的过程）"),
    "few-shot": ("fjuː ʃɒt", "少样本提示：给模型几个示例再提问"),
    "zero-shot": ("ˈzɪərəʊ ʃɒt", "零样本提示：不给示例直接提问"),
    "top-k": ("tɒp keɪ", "采样时只在概率最高的 k 个 token 里选"),
    "top-n": ("tɒp en", "取前 N 个结果"),
    "self-attention": ("self əˈtenʃn", "自注意力机制，序列内部互相计算相关性"),
    "multi-head": ("ˈmʌlti hed", "多头注意力：多组 Q/K/V 并行计算"),
    "prefix-tuning": ("ˈpriːfɪks ˈtjuːnɪŋ", "参数高效微调：只训练输入前缀向量"),
    "qlora": ("kjuː el ˈlɔːrə", "量化版 LoRA，显存更省的微调方案"),
    "rlhf": ("", "基于人类反馈的强化学习，读作 R-L-H-F"),
    "flashattention": ("flæʃ əˈtenʃn", "IO 感知的注意力计算优化算法"),
    "rerank": ("ˌriːˈræŋk", "重排序：对召回结果二次打分"),
    "reranker": ("ˌriːˈræŋkə", "重排序模型"),
    "cross-encoder": ("krɒs enˈkəʊdə", "交叉编码器：query 和文档拼接后一起输入模型打分"),
    "graphrag": ("ɡræf ræɡ", "GraphRAG：知识图谱增强的检索生成"),
    "hnsw": ("", "Hierarchical Navigable Small World，分层可导航小世界图，主流向量索引算法，读作 H-N-S-W"),
    "text-embedding": ("tekst ɪmˈbedɪŋ", "文本向量化"),
    "softmax": ("ˈsɒftmæks", "归一化函数，把 logits 转成概率分布"),
    "qk": ("", "注意力机制里的 Query / Key 矩阵"),
    "llm-as-judge": ("", "让大模型当裁判给答案打分的评估方式"),
    "llm-as-a-judge": ("", "让大模型当裁判给答案打分的评估方式"),
    "human-in-the-loop": ("", "人在回路：关键步骤由人工确认后再继续"),
    "multi-agent": ("ˈmʌlti ˈeɪdʒənt", "多智能体协作"),
    "plan-and-execute": ("plæn ənd ˈeksɪkjuːt", "先整体规划、再逐步执行的 Agent 范式"),
    "openai": ("ˌəʊpən eɪ aɪ", "OpenAI 公司及其 API"),
    "chatbot": ("ˈtʃætbɒt", "聊天机器人"),

    # ---- 高频：Python 生态 ----
    "cpython": ("ˌsiː ˈpaɪθən", "官方 C 语言实现的 Python 解释器"),
    "jython": ("ˈdʒaɪθən", "运行在 JVM 上的 Python 实现"),
    "ironpython": ("ˈaɪən ˈpaɪθən", "基于 .NET 的 Python 实现"),
    "asyncio": ("eɪˈsɪŋkiːəʊ", "Python 异步 I/O 标准库，常读 async-io"),
    "functools": ("ˈfʌŋktuːlz", "Python 高阶函数工具库（lru_cache、partial、wraps）"),
    "itertools": ("ˈaɪtətuːlz", "Python 迭代器工具库"),
    "contextlib": ("ˈkɒntekst lɪb", "Python 上下文管理工具库"),
    "contextmanager": ("ˈkɒntekst ˈmænɪdʒə", "contextlib 的装饰器，把生成器变成上下文管理器"),
    "weakref": ("wiːk ref", "Python 弱引用模块，不阻止垃圾回收"),
    "deepcopy": ("diːp ˈkɒpi", "深拷贝（copy 模块），递归复制所有子对象"),
    "namedtuple": ("neɪmd ˈtʌpl", "collections 的具名元组"),
    "defaultdict": ("dɪˈfɔːlt dɪkt", "collections 的带默认值字典"),
    "frozenset": ("ˈfrəʊzn set", "Python 不可变集合"),
    "datetime": ("deɪt taɪm", "Python 日期时间模块"),
    "kwargs": ("kwɑːrɡz", "Python 关键字参数（**kwargs），也常读 k-w-args"),
    "argv": ("ɑːrɡ viː", "命令行参数列表（sys.argv）"),
    "getattribute": ("ɡet əˈtrɪbjuːt", "Python 属性访问的 dunder 方法 __getattribute__"),
    "stopiteration": ("stɒp ˌɪtəˈreɪʃn", "迭代器耗尽时抛出的异常"),
    "baseexception": ("beɪs ɪkˈsepʃn", "Python 所有异常的基类"),
    "nameerror": ("neɪm ˈerə", "使用未定义变量时抛出的异常"),
    "keyboardinterrupt": ("ˈkiːbɔːd ˌɪntəˈrʌpt", "按 Ctrl+C 触发的异常"),
    "threadpoolexecutor": ("θred puːl ɪɡˈzekjətə", "concurrent.futures 的线程池"),
    "mypy": ("ˈmaɪpiː", "Python 静态类型检查工具"),
    "pyright": ("ˈpaɪraɪt", "微软出品的 Python 类型检查器"),
    "pydantic": ("paɪˈdæntɪk", "Python 数据校验与设置管理库"),
    "typeddict": ("taɪpt dɪkt", "typing 的 TypedDict：给字典加类型标注"),
    "fastapi": ("fɑːst eɪ piː aɪ", "Python 高性能 Web 框架，常读 fast-A-P-I"),
    "starlette": ("stɑːˈlet", "FastAPI 底层的轻量 ASGI 框架"),
    "uvicorn": ("ˈjuːvɪkɔːn", "Python ASGI 服务器"),
    "gunicorn": ("ˈɡuːnɪkɔːn", "Python WSGI HTTP 服务器"),
    "asgi": ("", "Asynchronous Server Gateway Interface，异步网关接口，读作 A-S-G-I"),
    "wsgi": ("ˈwɪzɡiː", "Web Server Gateway Interface，Python Web 网关接口"),
    "streamingresponse": ("ˈstriːmɪŋ rɪˈspɒns", "FastAPI 的流式响应类"),
    "numpy": ("ˈnʌmpaɪ", "Python 数值计算库"),
    "dataframe": ("ˈdeɪtəfreɪm", "pandas 的二维表格数据结构"),
    "mixin": ("ˈmɪksɪn", "混入类：通过多重继承复用小功能"),
    "legb": ("", "Python 名字查找顺序：Local→Enclosing→Global→Built-in，读作 L-E-G-B"),

    # ---- 高频：网络 / 前端 / 运维 ----
    "nginx": ("en dʒɪn ˈeks", "高性能 Web 服务器和反向代理"),
    "websocket": ("ˈwebsɒkɪt", "全双工长连接协议"),
    "eventsource": ("ɪˈvents sɔːs", "浏览器接收 SSE 服务器推送的 API"),
    "keep-alive": ("kiːp əˈlaɪv", "HTTP 长连接：复用 TCP 连接"),
    "keepalivetime": ("", "保活时长参数（TCP keepalive 或线程池空闲回收）"),
    "uuid": ("juː juː aɪ diː", "通用唯一标识符，也有人读 /ˈjuːɪd/"),
    "serverhello": ("sɜːvə həˈləʊ", "TLS 握手中服务端返回的问候消息"),
    "clienthello": ("ˈklaɪənt həˈləʊ", "TLS 握手中客户端发出的问候消息"),
    "ecdhe": ("", "椭圆曲线临时 DH 密钥交换算法，提供前向 secrecy，读作 E-C-D-H-E"),
    "rwnd": ("", "TCP 接收窗口（receive window），读作 R-W-N-D"),
    "json-rpc": ("", "用 JSON 编码的远程调用协议"),
    "webhook": ("ˈwebhʊk", "Web 回调：事件发生时主动请求你预留的 URL"),
    "try-catch": ("traɪ kætʃ", "异常捕获结构"),
    "supervisor-worker": ("ˈsuːpəvaɪzə ˈwɜːkə", "监督者-工作者进程模型：主进程管子进程"),
    "hashmap": ("ˈhæʃmæp", "Java 的哈希表 Map 实现"),
    "concurrenthashmap": ("kənˈkʌrənt hæʃmæp", "Java 的线程安全哈希表"),
    "hashcode": ("hæʃ kəʊd", "Java 对象的哈希值方法 hashCode()"),
    "threadfactory": ("θred ˈfæktri", "Java 线程工厂，定制线程的创建"),
    "maximumpoolsize": ("", "Java 线程池参数：最大线程数"),
    "corepoolsize": ("", "Java 线程池参数：核心线程数"),
    "rejectedexecutionhandler": ("", "Java 线程池的拒绝策略处理器"),
    "messagequeueselector": ("", "RocketMQ 的队列选择器，顺序消息用它固定队列"),
    "pinia": ("ˈpiːnjə", "Vue 官方状态管理库"),
    "defineproperty": ("dɪˈfaɪn ˈprɒpəti", "JavaScript 的 Object.defineProperty，精细定义对象属性"),
    "cssom": ("", "CSS Object Model，CSS 对象模型，读作 C-S-S-O-M"),
    "dockerfile": ("ˈdɒkəfaɪl", "Docker 镜像的构建描述文件"),
    "cgroup": ("ˈsiːɡruːp", "Linux 控制组，容器资源隔离与限制的基础"),
    "workqueue": ("wɜːk kjuː", "工作队列（K8s 控制器 / 并发模式）"),
    "yml": ("ˈjæməl", "YAML 配置文件扩展名，读法同 yaml"),
    "docx": ("dɒks", "Word 文档格式"),
    "leetcode": ("ˈliːtkəʊd", "算法刷题平台"),
    "epoll": ("ˈiːpɒl", "Linux 的 I/O 多路复用机制"),
    "groupby": ("ɡruːp baɪ", "分组聚合操作"),
    "grafana": ("ɡrəˈfɑːnə", "开源监控可视化平台"),
    "rnn": ("", "循环神经网络，读作 R-N-N"),
    "tf-idf": ("", "词频-逆文档频率，传统文本特征权重算法，读作 T-F-I-D-F"),

    # ---- 覆盖：ECDICT 收录但在技术语境下误导的词（补充表优先于 ECDICT）----
    "agent": ("ˈeɪdʒənt", "（大模型）智能体：能自主规划、调用工具的 AI 程序"),
    "transformer": ("trænsˈfɔːmə", "Transformer 架构：基于自注意力的大模型基础架构"),
    "shard": ("ʃɑːd", "分片：把数据水平拆分到多个节点（sharding）"),
    "token": ("ˈtəʊkən", "模型处理文本的最小单位，API 按它计费、上下文按它限量"),
    "prompt": ("prɒmpt", "提示词：发给模型的输入文本"),
    "embedding": ("ɪmˈbedɪŋ", "嵌入：把文本变成向量的过程/结果"),
    "chunk": ("tʃʌŋk", "文本块：文档切分后的片段"),
    "chain": ("tʃeɪn", "链：把多个步骤串起来的调用链（LangChain 的 Chain）"),
    "grounding": ("ˈɡraʊndɪŋ", "落地：让模型的回答基于检索到的事实，减少幻觉"),
    "fine-tuning": ("faɪn ˈtjuːnɪŋ", "微调：在预训练模型基础上用领域数据继续训练"),
    "tuning": ("ˈtjuːnɪŋ", "调优/微调"),
    "pipeline": ("ˈpaɪplaɪn", "流水线：按序串联的处理流程"),
    "streaming": ("ˈstriːmɪŋ", "流式输出：边生成边返回，而不是等全部生成完"),
    "scheduler": ("ˈʃedjuːlə", "调度器：决定任务何时/在哪个资源上运行"),
    "orchestration": ("ˌɔːkɪˈstreɪʃn", "编排：协调多个组件/服务协同完成一个流程"),
    "callback": ("ˈkɔːlbæk", "回调函数：传给别人的函数，到时机由对方调用"),
    "handler": ("ˈhændlə", "处理器/处理函数：负责处理某类事件"),
    "wrapper": ("ˈræpə", "包装器：在原有功能外面包一层增强逻辑"),
    "decorator": ("ˈdekəreɪtə", "装饰器：Python 的 @语法，给函数包一层增强逻辑"),
    "hook": ("hʊk", "钩子：框架预留的扩展点，在特定时机被调用"),
    "mock": ("mɒk", "测试替身：模拟真实对象的行为"),
    "stub": ("stʌb", "桩：测试里的简易替代实现，返回固定结果"),
    "fixture": ("ˈfɪkstʃə", "pytest 的测试装置：负责前置准备和清理"),
    "master": ("ˈmɑːstə", "主节点/主库（主从架构里负责写的那个）"),
    "slave": ("sleɪv", "从节点/从库（现多改称 replica）"),
}


def main() -> int:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(root, "data", "ecdict.db")
    if not os.path.exists(db_path):
        print(f"ecdict.db not found at {db_path}", file=sys.stderr)
        return 1
    con = sqlite3.connect(db_path)
    con.execute(
        "CREATE TABLE IF NOT EXISTS supplement ("
        "word TEXT PRIMARY KEY, phonetic TEXT, translation TEXT)"
    )
    con.execute("DELETE FROM supplement")
    con.executemany(
        "INSERT INTO supplement (word, phonetic, translation) VALUES (?, ?, ?)",
        sorted((w, p, t) for w, (p, t) in ENTRIES.items()),
    )
    con.commit()
    total = con.execute("SELECT count(*) FROM supplement").fetchone()[0]
    print(f"supplement table rebuilt: {total} entries in {db_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
