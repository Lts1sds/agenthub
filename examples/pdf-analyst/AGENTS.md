# pdf-analyst

PDF 论文/文档分析助手。安装后 skills 会注入你的 agent 运行时（comagic / claude-code），
直接对运行时说"帮我分析这篇 PDF"即可触发 pdf-analysis 技能。

## 能力

- 提取论文结构：标题、作者、发表信息
- 归纳问题、方法、结果、结论四要素
- 输出可引用的要点清单（所有数字来自原文，禁止推测）

## 依赖模型

- deepseek-chat（或任意兼容模型，经中转站调用）
