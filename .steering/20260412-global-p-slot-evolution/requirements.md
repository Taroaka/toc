# Global P-Slot Evolution

- 新しい workflow 修正が特定 run の場当たり対応で終わらず、以後の全物語でも同じ `p-slot` を通る共通 contract に昇格できること
- 新しい `p-slot` が必要になったとき、番号は全作品共通で存在し、各 run では `required|optional|skipped` を持てること
- `skip` は例外ではなく正規状態として扱い、`p000_index.md` と `state.txt` から「今回は何を通り、何を飛ばしたか」を読めること
- 新しい `p-slot` を追加するときに、どの正本を更新すべきかが明確であること
- slot 追加漏れを減らすため、少なくとも docs / state / run index の更新対象に対して再現可能な手順と検証があること
- 全体設計の変更は `.steering/YYYYMMDD-<title>/requirements.md -> design.md -> tasklist.md` の手順で扱い、rule なしの場当たり更新にしないこと
