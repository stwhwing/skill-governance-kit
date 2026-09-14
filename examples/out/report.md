# 技能治理综合报告 (report)

- **sources**: hermes, openclaw
- **total**: 5
- **usage_window**: 2025-01-01

## 全量技能清单

| skill_id | name | ecosystem | presence | category | path | created_at | version | description | use_count | evidence_source | mirror_of | drift |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| hermes:archive-demo-old | demo-old | hermes | archived | .archive | skills/.archive/demo-old | - | 0.1.0 | Archived demo skill retained for evolution evidence. | 0 | none | - | - |
| hermes:demo-alpha | demo-alpha | hermes | active | demo-alpha | skills/demo-alpha | - | 1.0.0 | Alpha demo skill for governance tests. | 7 | usage_json | openclaw:demo-alpha | clean |
| hermes:demo-beta | demo-beta | hermes | active | demo-beta | skills/demo-beta | - | 2.0.0 | Beta demo skill that is never used in the fixture window. | 0 | usage_json | - | - |
| openclaw:demo-alpha | demo-alpha | openclaw | active | demo-alpha | workspace/skills/demo-alpha | - | 1.0.0 | Alpha demo skill for governance tests. | 1 | trajectory | hermes:demo-alpha | clean |
| openclaw:demo-gamma | demo-gamma | openclaw | active | demo-gamma | workspace/skills/demo-gamma | - | 1.2.0 | Gamma demo skill exercised through trajectory evidence. | 1 | trajectory | - | - |

## 零使用清单 (window=2025-01-01)

| skill_id | name | ecosystem | presence | use_count | last_used_at | evidence_source | confidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| hermes:archive-demo-old | demo-old | hermes | archived | 0 | - | none | C |
| hermes:demo-beta | demo-beta | hermes | active | 0 | - | usage_json | A |
| openclaw:demo-alpha | demo-alpha | openclaw | active | 1 | - | trajectory | A |
| openclaw:demo-gamma | demo-gamma | openclaw | active | 1 | - | trajectory | A |

## 已使用清单 (window=2025-01-01)

| skill_id | name | ecosystem | presence | use_count | last_used_at | evidence_source | confidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| hermes:demo-alpha | demo-alpha | hermes | active | 7 | 2025-02-01T00:00:00Z | usage_json | A |

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
