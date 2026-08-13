# 题库 JSON 格式说明

本目录存放清洗后的结构化题库文件，每个 `.json` 文件对应一个技术栈或主题，文件内容为题目对象数组。字段与数据库 `questions` 表一一对应，导入时逐条写入。

## 文件格式

顶层为 JSON 数组，每个元素是一道题：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `stem` | string | 是 | 标准题干 |
| `answer` | string | 是 | 标准答案（Markdown 均可） |
| `tech_stack` | string | 是 | 技术栈：`python` / `agent` / `vue3` |
| `difficulty` | string | 否 | 难度：`basic` / `medium` / `hard`，默认 `medium` |
| `keywords` | string[] | 否 | 关键词列表（评分时用于命中检测），默认 `[]` |
| `tags` | string[] | 否 | 标签列表（抽题筛选用），默认 `[]` |

`id`、`created_at` 由数据库生成，JSON 中不写。

## 示例

见本目录 `python_basic.example.json`。

## 追问组

追问组（`question_groups` 表）在题目入库后由题库管家 Agent 生成，JSON 文件中不定义；如需手工指定，可在后续 Phase 再约定格式。
