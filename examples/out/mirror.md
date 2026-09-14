# 双生态镜像对照 (mirror)

**generated_at**: 2026-09-14T01:48:15Z

- **pairs**: 1
- **clean**: 1
- **differs**: 0
- **unknown**: 0

## 镜像对（同名跨生态）

| name | hermes_skill_id | openclaw_skill_id | drift |
| --- | --- | --- | --- |
| demo-alpha | hermes:demo-alpha | openclaw:demo-alpha | clean |

---

> 口径声明：Hermes 使用 = skill_view 标准加载（不含 read_file / terminal 直读）。
> 口径声明：OpenClaw 使用 = 仅 trajectory 的 arguments.path 严口径计入 use_count；消息正文引用仅作旁证。
> 口径声明：OpenClaw 会话快照内嵌技能目录（skills.entries）永不 计入使用。
> 口径声明：全程只读采集；缺失数据源将降级并把原因记录到 warnings。
> 口径声明：同输入重复运行，输出除 generated_at 外逐字节一致（幂等）。

### 降级与告警（warnings）

- bad_jsonl: 1 malformed line(s) skipped
