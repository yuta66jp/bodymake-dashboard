import pandas as pd
import streamlit as st
from supabase import Client, create_client


# --- 0. 接続クライアント初期化 ---
@st.cache_resource
def init_connection() -> Client:
    try:
        url = st.secrets["connections"]["supabase"]["SUPABASE_URL"]
        key = st.secrets["connections"]["supabase"]["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Supabase connection failed: {e}")
        st.stop()


# --- 1. Daily Log 取得 (Read) ---
@st.cache_data(ttl=60)
def fetch_raw_data() -> pd.DataFrame:
    supabase = init_connection()
    try:
        # log_date の昇順で取得
        response = (
            supabase.table("daily_logs")
            .select("*")
            .order("log_date", desc=False)
            .execute()
        )
        df = pd.DataFrame(response.data)

        if df.empty:
            return pd.DataFrame(
                columns=["ds", "y", "Calories", "Protein", "Fat", "Carbs"]
            )

        # カラム名のマッピング (DB列名 -> アプリでの使用名)
        # アプリ側(logic.py等)は "ds", "y" を期待しているためここで変換
        rename_map = {
            "log_date": "ds",
            "weight": "y",
            "calories": "Calories",
            "protein": "Protein",
            "fat": "Fat",
            "carbs": "Carbs",
            "created_at": "ts",  # ソート順序保証用
        }
        df = df.rename(columns=rename_map)

        # 型変換
        df["ds"] = pd.to_datetime(df["ds"])
        df["y"] = pd.to_numeric(df["y"], errors="coerce")

        return df
    except Exception as e:
        st.error(f"Data fetch error: {e}")
        return pd.DataFrame()


# --- 2. 食品マスタ取得 (Read) ---
@st.cache_data(ttl=600)
def fetch_food_list():
    """
    Returns: {"白米": {"p": 2.5, "f": 0.3, "c": 37.1, "cal": 168}, ...}
    """
    supabase = init_connection()
    try:
        response = supabase.table("food_master").select("*").order("name").execute()
        data = response.data

        food_dict = {}
        for item in data:
            food_dict[item["name"]] = {
                "p": float(item.get("protein") or 0),
                "f": float(item.get("fat") or 0),
                "c": float(item.get("carbs") or 0),
                "cal": int(item.get("calories") or 0),
            }
        return food_dict
    except Exception:
        return {}


# --- 3. 過去CSV取得 (Read) ---
# Notion/Supabaseに関係なくローカルファイルなので、そのまま維持
@st.cache_data
def fetch_history_csv():
    import os

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


# --- 4. Daily Log 保存 (Upsert) ---
def add_daily_log(date_obj, weight, note, kcal=0, p=0, f=0, c=0):
    supabase = init_connection()

    # 登録データ
    record = {
        "log_date": str(date_obj),
        "weight": float(weight),
        "note": note,
        "calories": int(kcal),
        "protein": float(p),
        "fat": float(f),
        "carbs": float(c),
    }

    # log_dateをキーにしてUpsert (重複時は更新)
    supabase.table("daily_logs").upsert(record, on_conflict="log_date").execute()

    # キャッシュクリア
    fetch_raw_data.clear()


# --- 5. 食品マスタ登録 (Create) ---
def add_food_item(name, p, f, c, cal):
    supabase = init_connection()
    record = {
        "name": name,
        "calories": int(cal),
        "protein": float(p),
        "fat": float(f),
        "carbs": float(c),
    }
    supabase.table("food_master").upsert(record, on_conflict="name").execute()
    fetch_food_list.clear()


# --- 6. 設定値の取得 (Read) ---
@st.cache_data(ttl=60)
def fetch_settings():
    supabase = init_connection()
    try:
        response = supabase.table("settings").select("*").execute()
        settings = {}
        for item in response.data:
            key = item["key"]
            # 数値があれば数値を、なければ文字列を使用
            if item["value_num"] is not None:
                settings[key] = float(item["value_num"])
            else:
                settings[key] = item["value_str"]
        return settings
    except:
        return {}


# --- 7. 設定値の更新 (Upsert) ---
def update_setting(key, new_value):
    supabase = init_connection()

    record = {"key": key}
    if isinstance(new_value, (int, float)):
        record["value_num"] = float(new_value)
        record["value_str"] = None
    else:
        record["value_num"] = None
        record["value_str"] = str(new_value)

    supabase.table("settings").upsert(record, on_conflict="key").execute()
    fetch_settings.clear()


# --- 8. セットメニュー保存 (Upsert) ---
def save_menu_item(set_name, items_list):
    supabase = init_connection()
    # JSON型として保存
    record = {
        "name": set_name,
        "recipe": items_list,  # Supabase(Python lib)が自動でJSONシリアライズしてくれます
    }
    supabase.table("menu_master").upsert(record, on_conflict="name").execute()
    fetch_menu_list.clear()


# --- 9. セットメニュー取得 (Read) ---
@st.cache_data(ttl=600)
def fetch_menu_list():
    supabase = init_connection()
    try:
        response = supabase.table("menu_master").select("*").execute()
        menu_dict = {}
        for item in response.data:
            # item["recipe"] は既にPythonのリスト/辞書になっている
            menu_dict[item["name"]] = item["recipe"]
        return menu_dict
    except:
        return {}
