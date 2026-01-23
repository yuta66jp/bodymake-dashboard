import os
import time

import pandas as pd
import tomllib
from notion_client import Client

# --- 設定 ---
CSV_FILE = "past_data.csv"


def load_secrets():
    # .streamlit/secrets.toml を読み込む
    secret_path = os.path.join(".streamlit", "secrets.toml")
    try:
        with open(secret_path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        print("❌ エラー: .streamlit/secrets.toml が見つかりません。")
        exit()


def main():
    print("🚀 データインポートを開始します...")

    # 1. 認証情報の読み込み
    secrets = load_secrets()
    notion = Client(auth=secrets["NOTION_TOKEN"])
    db_id = secrets["DATABASE_ID"]

    # 2. CSVデータの読み込み
    try:
        # ヘッダーがあってもなくても対応できるように読み込む
        # namesを指定することで強制的に列名を固定
        df = pd.read_csv(CSV_FILE, header=None, names=["date", "weight"])

        # ★ここが改良点: エラー(文字など)は 'NaT' (無効値) に変換して、その行を消す
        # これで「ヘッダー行」や「空行」が自動的に削除されます
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"])  # 日付が無効な行を削除

        # 体重も数値以外は削除
        df["weight"] = pd.to_numeric(df["weight"], errors="coerce")
        df = df.dropna(subset=["weight"])

    except Exception as e:
        print(f"❌ CSV読み込みエラー: {e}")
        return

    total = len(df)
    print(f"📋 有効なデータ件数: {total}件")

    # 3. Notionへ送信
    success_count = 0
    for index, row in df.iterrows():
        try:
            # 時刻が含まれていても、ここで '%Y-%m-%d' にすることで日付のみにします
            date_str = row["date"].strftime("%Y-%m-%d")
            weight_val = row["weight"]

            # APIコール
            notion.pages.create(
                parent={"database_id": db_id},
                properties={
                    "Date": {"date": {"start": date_str}},
                    "Weight": {"number": weight_val},
                },
            )

            # 進捗表示
            print(
                f"[{success_count + 1}/{total}] ✅ {date_str}: {weight_val}kg 保存完了"
            )
            success_count += 1

            # API負荷軽減
            time.sleep(0.3)

        except Exception as e:
            print(f"❌ 送信エラー: {e}")

    print("-" * 30)
    print(f"🎉 インポート完了: {success_count} / {total} 件")


if __name__ == "__main__":
    main()
