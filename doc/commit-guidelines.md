# 提交规范（Conventional Commits）

统一采用 [Conventional Commits](https://www.conventionalcommits.org/) 语法，格式如下：

```
<type>(<scope>): <summary>
```

- **type**：常用类型 `feat`（功能）、`fix`（修复）、`docs`、`chore`、`refactor`、`test`、`build`、`perf` 等。
- **scope**：可选，建议填写模块名称（如 `orders`、`payments`、`infra`），便于定位。
- **summary**：一句话描述变更意图，使用祈使句小写开头（不超过 72 个字符）。

额外要求：

1. 一个提交只做一类变更；数据结构或迁移必须分离提交并附带回滚说明。
2. 若引入破坏性变更，在尾部增加 `!`（例如 `feat(order)!: require payment_channel field`）并在正文中说明 BREAKING CHANGE。
3. 在正文列出变更背景、影响范围、验证方式（如测试命令、压测截图）。
4. 与 Issue/需求关联时，在正文末尾使用 `Refs #<id>` 或 `Fixes #<id>`。

规范提交信息有助于自动生成变更日志、触发 CI 规则，并提升代码审查效率。
