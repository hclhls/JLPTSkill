請產生 JLPT N1/N2 可能考的日文擬聲詞與擬態語 100 個的學習資料，輸出到 `out/jlpt-n1n2-onomatopoeia`。

需求：

- 產生符合 `source.json` schema 的資料。
- 每筆包含日文、讀音、繁中解釋、日文例句、繁中翻譯、回想提示、相近詞、對比備註。
- JLPT 級別若非官方來源確認，標記為推定。
- `verification_status` 預設為 `needs_review`。
- 產出 Obsidian Markdown、Anki 雙向卡、字幕、旁白文字與影片素材。
- TTS 預設使用 edge-tts；不需要 API key，無法產生語音時可降級成無聲影片素材。
