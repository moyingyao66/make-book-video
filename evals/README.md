# 评估闭环

本目录保存评估规范，不保存虚构的宿主表现。`skill-evals.json` 是固定测试集；它不是一次评估结果，也不是 baseline。

## 固定触发测试集

- 共 20 条 prompt：10 条应使用 `make-book-video`，10 条应跳过并走各自的 `expectedRoute`。
- 每条 prompt 必须在目标宿主中独立运行 3 次，共 60 次。每次使用全新会话，不继承上一轮消息、已读 Skill 或手工提示。
- 正例同时覆盖显式双交付和自然的隐含双交付，例如成片发布后还要换图、换封面、改字幕或复用再发；普通成片需求及明确“只要 MP4/不要工程”的请求仍应走 `book-sales-video`。
- `minimumUseCaseSuccessRate`、`minimumExpectedRouteRate` 和 `minimumCaseStabilityRate` 都是 `1.0`：任何一个正例不能被聚合平均掩盖，负例不能稳定地走错路线，同一 prompt 的三次 `triggered` 与 `selectedSkill` 也必须同时一致。

## 生成并记录真实结果

先从当前测试集生成空白记录，不要复制预期值来填充：

```bash
python3 scripts/score_trigger_evals.py --init-results /absolute/path/trigger-results.json
```

开始运行前填写：

- `targetHost`：实际执行路由的宿主名称，例如 Codex Desktop。
- `targetHostVersion`：可复现的版本号或 build 标识，必须包含版本/构建数字；`latest`、`current`、`unknown`、`fixture`、`test` 等占位值会被拒绝。
- `evaluationDate`：实际运行日期，格式为 `YYYY-MM-DD`，不能晚于评分当天。
- `suiteVersion`、`suiteSha256` 和 `runsPerPrompt` 由生成器写入，不要手改。SHA-256 会把结果绑定到测试集的确切内容。

逐条复制原始 prompt 到目标宿主的全新会话，并根据宿主的真实路由痕迹记录三次结果：

- 只有宿主实际选择 `make-book-video` 时，`triggered` 才填 `true`。
- `selectedSkill` 表示这次请求最终的 **owning Skill**：即负责统筹并交付整个任务的一个 Skill/路由 slug，不是执行中顺带调用的辅助 Skill 列表。必须填宿主真实路由，不要根据 `expectedRoute` 倒填答案；前导 `$` 可省略。
- 宿主未选择任何 Skill 时，明确填 `none`；空字符串表示尚未记录，会被评分器拒绝。
- 每次运行必须在对应位置填写 `runEvidence.sessionId`、`runEvidence.recordPath` 和 `runEvidence.recordSha256`。全部 60 个 session ID 与记录路径都必须唯一。
- `recordPath` 是相对于结果 JSON 所在目录的 `.json` 路径，不能是绝对路径、不能包含 `..`，也不能通过符号链接跳出该目录。`recordSha256` 是该原始记录当时的小写 SHA-256。
- 原始记录 JSON 至少要保留 `caseId`、`runIndex`（1 开始）、`sessionId`、`triggered` 和 `selectedSkill`；也应在其他字段中保留宿主真实路由记录或导出痕迹。五个必填字段必须与汇总文件的当前 case/运行序号/会话/触发值/最终 owning Skill 逐项一致。
- 若宿主实际 slug 与测试集约定不同，应先审查并版本化测试集，而不是在结果里改名掩盖差异。

单次原始记录的最小结构如下（可以增加宿主原始字段，不要删除这些绑定字段）：

```json
{
  "caseId": "use-title-first-later-image-swap",
  "runIndex": 1,
  "sessionId": "actual-host-session-id",
  "triggered": true,
  "selectedSkill": "make-book-video"
}
```

完成后评分：

```bash
python3 scripts/score_trigger_evals.py --results /absolute/path/trigger-results.json
```

评分器会实际打开 60 份原始记录，重算 SHA-256，并拒绝宿主/版本/日期缺失或不可复现、未来日期、套件指纹不匹配、case 缺失/重复/额外、三次值不完整、证据重复/缺失/过期/越界、证据内容与汇总不一致，以及 `triggered` 与 `selectedSkill` 自相矛盾的记录。报告同时给出触发率、最差正例成功率、误触发率、预期路线率、三次稳定率和逐 case 明细。

## 执行断言

对一个真实项目按它已到达的阶段运行：

```bash
python3 scripts/score_execution_evals.py /absolute/path/project --stage draft
python3 scripts/score_execution_evals.py /absolute/path/project --stage synthesis
python3 scripts/score_execution_evals.py /absolute/path/project --stage render
python3 scripts/score_execution_evals.py /absolute/path/project --stage release
```

阶段是累积的：`draft` 检查启动策略、内容契约和审批输出；`synthesis` 再检查审批回执；`render` 再检查冻结素材、豆包 provider timestamps 和当前渲染产物；`release` 再检查确定性 `editor-plan.json`、可编辑交付、最终媒体 QA 与发布新鲜度。每个 `executionAssertions[].stage` 必须与评分器在该阶段实际执行的 gate 一一对应，缺少声明、漏跑声明或多跑未声明 gate 都会失败。

`rendered-artifacts` 必须验证 `build_report.json` 中的 `audioMixSha256` 与实际混音文件一致。`final-media-qa` 还必须验证完整解码与人工复核通过、`audio.packetHashMatches=true`、混音文件存在，并且 `qa-report.audio.mixSha256` 与该文件一致。

## Baseline 规则

仓库刻意不提交由预期答案合成的“完美 baseline”。单元测试中的合成数组和证据文件只验证评分器会正确放行或拒绝输入，不能代表任何宿主的真实触发表现。SHA-256 只能证明评分时读取的文件未与汇总记录脱节，不能单独证明宿主运行的真实性。只有完成上述 60 次真实独立运行并保留目标宿主、精确版本、日期和原始证据后，结果文件才可以作为带来源的观测快照；不得把模板、推测或单元测试夹具宣称为 baseline。
