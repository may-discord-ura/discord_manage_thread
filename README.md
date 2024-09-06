# discord_manage_thread
フォーラムでのスレッド作成と管理、時限停止・削除を行うbot

## 機能
### スラッシュコマンド
- `/スレ立て`：設定した内容でスレッドを作成する。
  - コマンド実行後にタイトル・本文入力用のモーダルを表示
  - 自動ロック・削除までの時間設定も可能
- `/スレ管理`：スレ立て機能で作成したスレッド内で使用することで自動ロック・削除までの時間変更等を行う
### その他
- 作成したスレッドの自動ロック・削除
  - ロック5分前にアラートなど
### 動作イメージ
![image](https://github.com/user-attachments/assets/c96adb31-3b76-46db-b3f7-00454b1d4492)
![image](https://github.com/user-attachments/assets/b0a5cd44-d707-4642-9b9b-58eca47371eb)

## 導入準備
### discord側の準備
- 開発者ポータルからbotを作成する
  - トークンを確保
### サーバーの設定
- 環境変数`TOKEN`にbotのトークンを入れておく
  - 面倒な場合は`main.py`最終行の`"TOKEN"`に直接トークンを入れる
### botの設定
- なし

## 実行
run main.py

## 動作補足
- `/スレ立て`及び`/スレ管理`コマンドの結果は`/config/created_thread.json`に保管される
- 5分ごとのループで`/config/created_thread.json`内のスレッドIDをキーに検索、記録された時間と現時刻との差分で処理を実行する

## 備考
なし
