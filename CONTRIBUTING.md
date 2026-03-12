# Contributing

感谢你改进 `openclaw-multiagent-framework`。

## 贡献范围

欢迎提交：
- 文档修正
- 示例补充
- 接入指引优化
- 术语统一
- 开源包与内部运行版差异说明补充

当前仓库以 **协议、模板、文档框架** 为主；内部实现代码暂不在本仓库直接维护。

## 提交流程

1. Fork 仓库
2. 创建分支
   ```bash
   git checkout -b docs/improve-readme
   ```
3. 提交修改
   ```bash
   git commit -m "docs: improve README navigation"
   ```
4. 推送分支并创建 PR

## 建议的提交粒度

请尽量保持 **小步提交**：
- 一个 commit 只解决一个主题
- 文档修正与结构重构尽量分开
- 若修改了示例命令，请同时更新相关说明文档

## 文档修改检查清单

- [ ] README / QUICKSTART / GETTING_STARTED 之间的命令一致
- [ ] 路径使用统一命名
- [ ] 占位符写法一致（如 `<task_id>` / `<channel-id>`）
- [ ] 中英文术语没有互相冲突
- [ ] 若修改能力分层，同时更新 `CAPABILITY_LAYERS.md`

## Issues

请优先使用 Issue 模板：
- Bug Report
- Feature Request

## 设计原则

1. **协议优先**：先把协作规则讲清楚
2. **小步可用**：优先最小可用集合，再谈完整产品化
3. **脱敏优先**：开源内容不包含内部敏感配置
4. **真值清晰**：明确区分文档框架、内部实现、Core 缺口
