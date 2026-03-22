# IFLOW.md

这是一个 EDA 项目。

规则：
- 只允许在指定任务目录内修改文件
- 除非 prompt 明确允许，不得修改 scripts/
- 不允许删除文件
- 输出必须简洁，列出 changed_files 和 summary
- 若任务是 RTL，只允许修改 rtl/
- 若任务是 TB，只允许修改 tb/
- 若任务是 Verification，只允许修改 verif/
- Build / Integration 优先执行固定脚本入口，不要自由发挥命令
