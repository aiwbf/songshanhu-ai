# Eval Groundedness Judge Skeleton

检查点：

- 回答是否引用了真实证据字段
- 回答是否把历史资料冒充为当前政策
- 回答是否越过证据给出资格结论
- 回答顺序是否符合“类别 -> 依据 -> 步骤”
- 当低置信度时是否正确补问或转人工

输出：

- pass / fail
- failure_reason
- risky_sentences
- missing_evidence_fields
