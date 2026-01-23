import json
import os

import pandas as pd
import streamlit as st
from notion_client import Client


# --- 1. Daily Log 取得 (Read) ---
@st.cache_data(ttl=3600)
def fetch_raw_data(db_id, token):
    try:
        notion = Client(auth=token)
        results = []
        has_more = True
        cursor = None
        while has_more:
            # 日付順で取得
            resp = notion.databases.query(
                database_id=db_id,
                start_cursor=cursor,
                sorts=[{"property": "Date", "direction": "ascending"}],
            )
            results.extend(resp["results"])
            has_more = resp["has_more"]
            cursor = resp["next_cursor"]

        data = []
        for page in results:
            try:
                props = page["properties"]
                d = props["Date"]["date"]["start"]
                w = props["Weight"]["number"]

                # 作成日時 (同日のデータ順序保証用)
                created_time = page["created_time"]

                if d and w is not None:
                    row = {"ds": d, "y": w, "ts": created_time}

                    # 栄養素の取得 (無い場合はNaN)
                    # Notionの列名: Calories, Protein, Fat, Carbs に対応
                    row["Calories"] = props.get("Calories", {}).get("number")
                    row["Protein"] = props.get("Protein", {}).get("number")
                    row["Fat"] = props.get("Fat", {}).get("number")
                    row["Carbs"] = props.get("Carbs", {}).get("number")

                    data.append(row)
            except:
                continue

        df = pd.DataFrame(data)
        if df.empty or "ds" not in df.columns:
            return pd.DataFrame(columns=["ds", "y"])

        df["ds"] = pd.to_datetime(df["ds"])

        # 日付 -> 作成日時 の順でソート
        df = df.sort_values(["ds", "ts"], ascending=[True, True])

        return df
    except Exception as e:
        st.error(f"Connection Error: {e}")
        return pd.DataFrame(columns=["ds", "y"])


# --- 2. 食品マスタ/セットメニュー取得 (Read) ---
@st.cache_data(ttl=600)
def fetch_food_list(food_db_id, token):
    """
    食材リストを取得して辞書で返す (Notion列名: Name, Calories, Protein, Fat, Carbs)
    """
    try:
        notion = Client(auth=token)
        results = []
        has_more = True
        cursor = None

        while has_more:
            kwargs = {"database_id": food_db_id}
            if cursor:
                kwargs["start_cursor"] = cursor
            resp = notion.databases.query(**kwargs)
            results.extend(resp["results"])
            has_more = resp["has_more"]
            cursor = resp["next_cursor"]

        food_dict = {}
        for page in results:
            try:
                props = page["properties"]
                # タイトル列
                name = props["Name"]["title"][0]["text"]["content"]

                # 数値列 (Calories, Protein, Fat, Carbs)
                cal = props.get("Calories", {}).get("number", 0)
                p = props.get("Protein", {}).get("number", 0)
                f = props.get("Fat", {}).get("number", 0)
                c = props.get("Carbs", {}).get("number", 0)

                # Noneの場合は0にする安全策
                cal = cal if cal is not None else 0
                p = p if p is not None else 0
                f = f if f is not None else 0
                c = c if c is not None else 0

                food_dict[name] = {"p": p, "f": f, "c": c, "cal": cal}
            except:
                continue
        return food_dict
    except Exception:
        # エラー時は空辞書を返す
        return {}


# --- 3. 過去CSV取得 (Read) ---
@st.cache_data
def fetch_history_csv():
    if not os.path.exists("history.csv"):
        return None
    try:
        df = pd.read_csv("history.csv")
        df["Date"] = pd.to_datetime(df["Date"])
        df["TargetDate"] = pd.to_datetime(df["TargetDate"])
        df["days_out"] = (df["Date"] - df["TargetDate"]).dt.days
        return df
    except:
        return None


# --- 4. Daily Log 保存 (Create) ---
# app.py では `add_daily_log` という名前で呼んでいる箇所があるため、
# 関数名を統一するか、エイリアスを作っておくと安全です。
# ここでは add_daily_log として定義します。
def add_daily_log(db_id, token, date_obj, weight, note, kcal=0, p=0, f=0, c=0):
    notion = Client(auth=token)

    props = {
        "Date": {"date": {"start": str(date_obj)}},
        "Weight": {"number": weight},
        "Note": {"title": [{"text": {"content": note or ""}}]},
    }

    # ★修正: 0より大きい場合のみDBに書き込む
    # 0の場合は書き込まないので、Notion上は「空」になり、グラフ計算から除外される
    if kcal > 0:
        props["Calories"] = {"number": kcal}
    if p > 0:
        props["Protein"] = {"number": p}
    if f > 0:
        props["Fat"] = {"number": f}
    if c > 0:
        props["Carbs"] = {"number": c}

    notion.pages.create(parent={"database_id": db_id}, properties=props)

    # キャッシュクリア (即座にグラフに反映させるため)
    fetch_raw_data.clear()


# --- 5. 食品マスタ登録 (Create) ---
def add_food_item(food_db_id, token, name, p, f, c, cal):
    """
    NotionのFood Databaseに新しいアイテムを追加する
    列名: Name, Calories, Protein, Fat, Carbs
    """
    notion = Client(auth=token)
    notion.pages.create(
        parent={"database_id": food_db_id},
        properties={
            "Name": {"title": [{"text": {"content": name}}]},
            "Calories": {"number": cal},
            "Protein": {"number": p},
            "Fat": {"number": f},
            "Carbs": {"number": c},
        },
    )
    # キャッシュクリア (サイドバーのリストに即座に反映させるため)
    fetch_food_list.clear()


# --- 6. 設定値の取得 (Read) ---
@st.cache_data(ttl=60)
def fetch_settings(settings_db_id, token):
    try:
        notion = Client(auth=token)
        resp = notion.databases.query(database_id=settings_db_id)

        settings = {}
        for page in resp["results"]:
            try:
                props = page["properties"]
                key = props["Key"]["title"][0]["text"]["content"]

                val_num = props.get("Value", {}).get("number")
                val_str = props.get("ValueStr", {}).get("rich_text", [])

                if val_num is not None:
                    settings[key] = val_num
                elif val_str:
                    settings[key] = val_str[0]["text"]["content"]
            except:
                continue
        return settings
    except:
        return {}


# --- 7. 設定値の更新 (Update) ---
def update_setting(settings_db_id, token, key, new_value):
    notion = Client(auth=token)

    props = {}
    if isinstance(new_value, (int, float)):
        props["Value"] = {"number": new_value}
        props["ValueStr"] = {"rich_text": []}
    else:
        props["Value"] = {"number": None}
        props["ValueStr"] = {"rich_text": [{"text": {"content": str(new_value)}}]}

    query = notion.databases.query(
        database_id=settings_db_id, filter={"property": "Key", "title": {"equals": key}}
    )
    results = query["results"]

    if results:
        notion.pages.update(page_id=results[0]["id"], properties=props)
    else:
        props["Key"] = {"title": [{"text": {"content": key}}]}
        notion.pages.create(parent={"database_id": settings_db_id}, properties=props)

    fetch_settings.clear()


# --- 8. セットメニュー保存 (Menu DBへ：更新対応版) ---
def save_menu_item(menu_db_id, token, set_name, items_list):
    """
    Menu DBにセットを保存。同名が存在する場合は上書き更新する。
    """
    notion = Client(auth=token)
    recipe_json = json.dumps(items_list, ensure_ascii=False)

    # 1. 既存チェック (名前で検索)
    query = notion.databases.query(
        database_id=menu_db_id,
        filter={"property": "Name", "title": {"equals": set_name}},
    )
    results = query["results"]

    if results:
        # A. 存在する場合 -> 上書き更新 (Update)
        page_id = results[0]["id"]
        notion.pages.update(
            page_id=page_id,
            properties={"Recipe": {"rich_text": [{"text": {"content": recipe_json}}]}},
        )
    else:
        # B. 存在しない場合 -> 新規作成 (Create)
        notion.pages.create(
            parent={"database_id": menu_db_id},
            properties={
                "Name": {"title": [{"text": {"content": set_name}}]},
                "Recipe": {"rich_text": [{"text": {"content": recipe_json}}]},
            },
        )

    # キャッシュクリア
    fetch_menu_list.clear()


# --- 9. セットメニュー取得 (Menu DBから) ---
@st.cache_data(ttl=600)
def fetch_menu_list(menu_db_id, token):
    """
    Menu DBからレシピ一覧を取得して辞書で返す
    Returns: {"朝食A": [{"name":"白米", "amount":200}, ...], ...}
    """
    try:
        notion = Client(auth=token)
        results = []
        has_more = True
        cursor = None

        while has_more:
            resp = notion.databases.query(database_id=menu_db_id, start_cursor=cursor)
            results.extend(resp["results"])
            has_more = resp["has_more"]
            cursor = resp["next_cursor"]

        menu_dict = {}
        for page in results:
            try:
                props = page["properties"]
                name = props["Name"]["title"][0]["text"]["content"]

                # Recipeカラム(JSON)をパース
                recipe_objs = props["Recipe"]["rich_text"]
                if recipe_objs:
                    recipe_str = recipe_objs[0]["text"]["content"]
                    menu_dict[name] = json.loads(recipe_str)
            except:
                continue
        return menu_dict
    except:
        return {}
