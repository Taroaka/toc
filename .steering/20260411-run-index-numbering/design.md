# Design

- `toc/run_index.py` を追加し、stage registry / file classifier / markdown renderer を持たせる
- `p000_index.md` は `state.txt` と run dir の実ファイル inventory から自動生成する
- stage registry は `p100` 単位で大工程を定義し、`x10~x50` は stage ごとの actual slot meaning を持てる
- file classifier は root files と `assets/**`, `logs/**`, `scratch/**` を exact rule で `P#` と role に振り分ける
- `sync_run_status()` のたびに `p000_index.md` を再生成する
- request / concat だけ更新して state が動かないケースのために、`generate-assets-from-manifest.py` と `build-clip-lists.py` からも index 再生成を呼ぶ
- 第1段階では既存ファイル名は維持し、`p000_index.md` に numbered navigation を投影する
- docs は `p000_index.md` と numbering layer を正本として追記する
