# 技能使用清单 (usage)

- **total**: 5
- **used**: 3
- **window**: all-time
- **zero_usage**: 2

## 零使用清单 (window=all-time)

| skill_id | name | ecosystem | presence | use_count | last_used_at | evidence_source | confidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| hermes:archive-demo-old | demo-old | hermes | archived | 0 | - | none | C |
| hermes:demo-beta | demo-beta | hermes | active | 0 | - | usage_json | A |

## 已使用清单 (window=all-time)

| skill_id | name | ecosystem | presence | use_count | last_used_at | evidence_source | confidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| hermes:demo-alpha | demo-alpha | hermes | active | 7 | 2025-02-01T00:00:00Z | usage_json | A |
| openclaw:demo-alpha | demo-alpha | openclaw | active | 1 | - | trajectory | A |
| openclaw:demo-gamma | demo-gamma | openclaw | active | 1 | - | trajectory | A |

---

> 口径声明：Hermes 使用 = skill_view 标准加载（不含 read_file / terminal 直读）。
> 口径声明：OpenClaw 使用 = 仅 trajectory 的 arguments.path 严口径计入 use_count；消息正文引用仅作旁证。
> 口径声明：OpenClaw 会话快照内嵌技能目录（skills.entries）永不 计入使用。
> 口径声明：全程只读采集；缺失数据源将降级并把原因记录到 warnings。
> 口径声明：同输入重复运行，输出除 generated_at 外逐字节一致（幂等）。

### 降级与告警（warnings）

- bad_jsonl: 1 malformed line(s) skipped
