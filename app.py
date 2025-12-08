import streamlit as st
import sqlite3
import datetime

# ==============================
# DB 接続＆初期化
# ==============================
@st.cache_resource
def get_connection():
    conn = sqlite3.connect("diary_points.db", check_same_thread=False)
    return conn

def init_db(conn):
    cur = conn.cursor()

    # 日記テーブル
    cur.execute("""
    CREATE TABLE IF NOT EXISTS diary_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entry_date TEXT NOT NULL,
        mood TEXT,
        content TEXT,
        created_at TEXT NOT NULL
    )
    """)

    # タスクテーブル（嫌なこと・めんどいこと）
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        point_value INTEGER NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1
    )
    """)

    # ポイント履歴
    cur.execute("""
    CREATE TABLE IF NOT EXISTS points_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER NOT NULL,
        points INTEGER NOT NULL,
        done_at TEXT NOT NULL,
        FOREIGN KEY (task_id) REFERENCES tasks(id)
    )
    """)

    conn.commit()


# ==============================
# 共通関数
# ==============================
def get_total_points(conn):
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(points), 0) FROM points_log")
    total = cur.fetchone()[0]
    return total

def get_tasks(conn, active_only=True):
    cur = conn.cursor()
    if active_only:
        cur.execute("SELECT id, name, point_value FROM tasks WHERE is_active = 1 ORDER BY id")
    else:
        cur.execute("SELECT id, name, point_value, is_active FROM tasks ORDER BY id")
    return cur.fetchall()

def add_task(conn, name, point_value):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO tasks (name, point_value, is_active) VALUES (?, ?, 1)",
        (name, point_value),
    )
    conn.commit()

def log_points(conn, task_id, points):
    cur = conn.cursor()
    now = datetime.datetime.now().isoformat(timespec="seconds")
    cur.execute(
        "INSERT INTO points_log (task_id, points, done_at) VALUES (?, ?, ?)",
        (task_id, points, now),
    )
    conn.commit()

def save_or_update_diary(conn, entry_date, mood, content):
    """
    毎回、新しい日記として保存する
    （同じ日付でも何個でも溜まる仕様）
    """
    cur = conn.cursor()
    date_str = entry_date.isoformat()
    now = datetime.datetime.now().isoformat(timespec="seconds")

    cur.execute(
        "INSERT INTO diary_entries (entry_date, mood, content, created_at) VALUES (?, ?, ?, ?)",
        (date_str, mood, content, now),
    )
    conn.commit()

def get_recent_diaries(conn, limit=10):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT entry_date, mood, content, created_at
        FROM diary_entries
        ORDER BY entry_date DESC
        LIMIT ?
        """,
        (limit,),
    )
    return cur.fetchall()


# ==============================
# Streamlit メイン
# ==============================
def main():
    st.set_page_config(
        page_title="日記 & ごほうびポイント",
        page_icon="✨",
        layout="centered",
    )

    conn = get_connection()
    init_db(conn)

    st.title("📔 日記 & 🏅がんばりポイント アプリ")

    # サイドバー
    page = st.sidebar.radio(
        "メニュー",
        ("今日の日記を書く", "ポイントを貯める", "履歴・合計ポイントを見る", "タスク設定"),
    )

    # ======================
    # ページ1：日記
    # ======================
    if page == "今日の日記を書く":
        st.header("📔 今日の日記")

        today = datetime.date.today()
        entry_date = st.date_input("日付", value=today)

        mood = st.selectbox(
            "今日の気分",
            [
                "😊 いい感じ",
                "😐 ふつう",
                "😣 つかれた",
                "💢 イライラ",
                "😭 つらい",
                "🥳 めちゃくちゃ最高",
                "（未選択）",
            ],
            index=0,
        )

        content = st.text_area("今日あったこと・感じたこと", height=200)

        if st.button("この内容で保存する"):
            if content.strip() == "" and mood == "（未選択）":
                st.warning("なにか1つは入力・選択してから保存してね。")
            else:
                save_or_update_diary(conn, entry_date, mood, content)
                st.success("日記を保存しました 📝")

    # ======================
    # ページ2：ポイント
    # ======================
    elif page == "ポイントを貯める":
        st.header("🏅 嫌なこと・めんどいことをやったらポイントGET")

        total = get_total_points(conn)
        st.metric("いまの合計ポイント", f"{total} pt")

        st.subheader("1. すでに登録済みのタスクでポイント加算")

        tasks = get_tasks(conn, active_only=True)
        if not tasks:
            st.info("まだタスクが登録されていません。下の『新しいタスクを追加』から作ってね。")
        else:
            task_labels = [f"{t[1]}（{t[2]} pt）" for t in tasks]
            task_ids = [t[0] for t in tasks]
            task_points = {t[0]: t[2] for t in tasks}

            selected_index = st.selectbox(
                "今日はどの『がんばった！』をやった？",
                range(len(task_labels)),
                format_func=lambda i: task_labels[i],
            )

            if st.button("やった！ポイント加算する"):
                task_id = task_ids[selected_index]
                points = task_points[task_id]
                log_points(conn, task_id, points)
                new_total = get_total_points(conn)
                st.success(f"{points} pt 加算しました！ 合計 {new_total} pt 🎉")

        st.markdown("---")
        st.subheader("2. 新しいタスクを追加")

        new_task_name = st.text_input("タスク名（例：『苦手な電話をかける』）")
        new_task_point = st.number_input("1回やったときのポイント", min_value=1, max_value=100, value=10, step=1)

        if st.button("タスクを追加する"):
            if new_task_name.strip() == "":
                st.warning("タスク名を入力してね。")
            else:
                add_task(conn, new_task_name.strip(), int(new_task_point))
                st.success("タスクを追加しました！")

    # ======================
    # ページ3：履歴
    # ======================
    elif page == "履歴・合計ポイントを見る":
        st.header("📊 履歴・ポイント状況")

        total = get_total_points(conn)
        st.metric("いまの合計ポイント", f"{total} pt")

        st.subheader("最近の日記（直近10件）")
        diaries = get_recent_diaries(conn, limit=10)

        if not diaries:
            st.info("まだ日記がありません。『今日の日記を書く』から始めてみよう。")
        else:
            for entry_date, mood, content, created_at in diaries:
                # created_at から時刻 HH:MM を取り出す（例: 2025-12-08T14:35:12 → 14:35）
                time_label = ""
                if created_at and len(created_at) >= 16:
                    time_label = created_at[11:16]

                title = f"{entry_date} {time_label} ｜ {mood}"

                with st.expander(title):
                    st.write(content if content else "（本文なし）")
                    st.caption(f"保存日時: {created_at}")

    # ======================
    # ページ4：タスク設定
    # ======================
    elif page == "タスク設定":
        st.header("⚙️ タスク一覧・ON/OFF")

        cur = conn.cursor()
        all_tasks = get_tasks(conn, active_only=False)

        if not all_tasks:
            st.info("まだタスクが登録されていません。『ポイントを貯める』ページから追加してね。")
        else:
            for task_id, name, point_value, is_active in all_tasks:
                cols = st.columns([3, 1, 1])
                with cols[0]:
                    st.write(f"・{name}（{point_value} pt）")
                with cols[1]:
                    new_active = st.checkbox("有効", value=bool(is_active), key=f"active_{task_id}")
                with cols[2]:
                    st.write("")

                if new_active != bool(is_active):
                    cur.execute(
                        "UPDATE tasks SET is_active = ? WHERE id = ?",
                        (1 if new_active else 0, task_id),
                    )
                    conn.commit()
                    st.toast(f"『{name}』の状態を更新しました。", icon="✅")


if __name__ == "__main__":
    main()