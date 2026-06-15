08:10 台股完整盤前決策系統
==========================

功能
----
每天 08:10 推播台股盤前資訊到 Telegram：
- 美股四大指數：道瓊、NASDAQ、S&P500、費城半導體
- 日韓早盤：日本日經225、韓國 KOSPI
- 台指盤前判斷：偏多 / 偏空 / 震盪

專案路徑
--------
D:\Py\tw_preopen_decision_system

安裝
----
建議使用 conda 獨立環境：

conda create -n preopen python=3.11 -y
conda activate preopen
pip install -r requirements.txt

設定 Telegram
-------------
1. 複製 .env.example 為 .env
2. 在 .env 填入：
   - TELEGRAM_BOT_TOKEN
   - TELEGRAM_CHAT_ID

不要把 .env 推上 GitHub。

手動測試
--------
python D:\Py\tw_preopen_decision_system\tw_preopen_decision_system.py

工作排程器
----------
目前本機已設定工作排程：
- 任務名稱：每日盤前資訊
- 觸發：週一到週五 08:10
- 程式：D:\Py\tw_preopen_decision_system\run_tw_preopen_system.bat
- 起始位置：D:\Py\tw_preopen_decision_system

GitHub Actions
--------------
也可以由 GitHub Actions 自動發送：
- Workflow：.github/workflows/preopen-report.yml
- 啟動時間：台北時間週一到週五 07:55
- 發送時間：workflow 內等待到台北時間 08:10 後發送

GitHub repository secrets 需要設定：
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID

注意：GitHub Actions schedule 可能延遲；此 workflow 先提早啟動並等待到 08:10，以降低整點排隊造成的延遲。

注意事項
--------
- last_sent_state_preopen.json 用來避免同一天重複發送，不應提交。
- .env 含 Telegram secrets，不應提交。
