# Design

- fixed `p-slot` contract 自体はすでに repo に入っているため、今回の焦点は「新 slot を global workflow に昇格する運用と検証」を明示化すること
- 正本の更新対象を固定する
  - `docs/system-architecture.md`
  - `docs/how-to-run.md`
  - `docs/data-contracts.md`
  - `docs/orchestration-and-ops.md`
  - `docs/root-pointer-guide.md`
  - `workflow/state-schema.txt`
  - `toc/run_index.py`
  - 必要なら `scripts/toc-state.py`
- 新しい `p-slot` を追加するときの最小手順を定義する
  1. `.steering/...` で requirement / design / tasklist を作る
  2. fixed slot contract を docs と `toc/run_index.py` に追加する
  3. `slot.<code>.*` の state key を必要に応じて `workflow/state-schema.txt` と `scripts/toc-state.py` に反映する
  4. `p000_index.md` が新 slot を表示することを確認する
  5. pointer docs / tests を通す
- 今回は「slot 追加漏れを完全自動検出する専用 validator」までは入れず、まずは steering と docs で更新対象を固定する
- 次段階で必要なら、`validate-pointer-docs.py` とは別に `validate-slot-contract.py` を追加し、docs と `toc/run_index.py` の slot 一貫性を検査できる形へ進める
- run ごとの差分は slot meaning の変更ではなく、`slot.<code>.status` / `slot.<code>.requirement` / `slot.<code>.skip_reason` / `slot.<code>.note` で表す
