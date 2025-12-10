import streamlit as st
import sqlite3
import datetime

# ===== タイムゾーン（JST） =====
JST = datetime.timezone(datetime.timedelta(hours=9))

# ===== DB 接続と初期化 =====
@st.cache_resource
def get_connection():
    conn = sqlite3.connect("diary_points.db", check_same_thread=False)
    init_db(conn)
    return conn


def init_db(conn):
    cur = conn.cursor()

    # 日記テーブル（1日いくつでも書ける）
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS diary_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_date TEXT NOT NULL,
            entry_time TEXT,
            mood TEXT,
            content TEXT,
            created_at TEXT NOT NULL
        )
        """
    )

    # タスクテーブル
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            point_value INTEGER NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """
    )

    # ポイントログテーブル
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS points_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            points INTEGER NOT NULL,
            done_at TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        )
        """
    )

    conn.commit()


# ===== 日記関連 =====
def save_diary(conn, entry_date, entry_time, mood, content):
    """毎回 新しい日記として保存（同じ日付でも何個でも）"""
    cur = conn.cursor()
    date_str = entry_date.isoformat()
    time_str = entry_time.strftime("%H:%M:%S") if entry_time else None
    now = datetime.datetime.now(JST).isoformat(timespec="seconds")

    cur.execute(
        """
        INSERT INTO diary_entries (entry_date, entry_time, mood, content, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (date_str, time_str, mood, content, now),
    )
    conn.commit()


def get_recent_diaries(conn, limit=10):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT entry_date, entry_time, mood, content, created_at
        FROM diary_entries
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    )
    return cur.fetchall()


# ===== タスク・ポイント関連 =====
def get_tasks(conn, only_active=True):
    cur = conn.cursor()
    if only_active:
        cur.execute(
            "SELECT id, name, point_value FROM tasks WHERE is_active = 1 ORDER BY id"
        )
    else:
        cur.execute(
            "SELECT id, name, point_value, is_active FROM tasks ORDER BY id"
        )
    return cur.fetchall()


def add_task(conn, name, point_value):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO tasks (name, point_value, is_active) VALUES (?, ?, 1)",
        (name, point_value),
    )
    conn.commit()


def toggle_task_active(conn, task_id, new_active):
    cur = conn.cursor()
    cur.execute(
        "UPDATE tasks SET is_active = ? WHERE id = ?", (1 if new_active else 0, task_id)
    )
    conn.commit()


def log_points(conn, task_id, points):
    cur = conn.cursor()
    now = datetime.datetime.now(JST).isoformat(timespec="seconds")
    cur.execute(
        "INSERT INTO points_log (task_id, points, done_at) VALUES (?, ?, ?)",
        (task_id, points, now),
    )
    conn.commit()


def get_total_points(conn):
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(points), 0) FROM points_log")
    row = cur.fetchone()
    return row[0] if row and row[0] is not None else 0


# ===== メイン画面 =====
def main():
    st.set_page_config(page_title="日記 & ごほうびポイント", layout="centered")

    conn = get_connection()

    st.sidebar.title("メニュー")
    page = st.sidebar.radio(
        "ページを選んでね",
        ["今日の日記を書く", "ポイントを貯める", "履歴・合計ポイントを見る", "タスク設定"],
    )

    # 気分の選択肢
    mood_options = [
        "超しんどい",
        "しんどい",
        "ふつう",
        "よき",
        "最高",
        "超最高",
        "なし",
    ]

    # ===== 1) 今日の日記を書く =====
    if page == "今日の日記を書く":
        st.header("📝 今日の日記を書く")

        today = datetime.date.today()
        now_time = datetime.datetime.now(JST).time().replace(second=0, microsecond=0)

        entry_date = st.date_input("日付", value=today)
        entry_time = st.time_input("書いた時間", value=now_time)

        default_index = mood_options.index("最高") if "最高" in mood_options else 0
        mood = st.selectbox("今日の気分", mood_options, index=default_index)

        content = st.text_area("今日あったこと・気持ち", height=200)

        if st.button("この内容で保存する"):
            save_diary(conn, entry_date, entry_time, mood, content)
            st.success("日記を保存したよ！")

    # ===== 2) ポイントを貯める =====
    elif page == "ポイントを貯める":
        st.header("⭐ ポイントを貯める")

        tasks = get_tasks(conn, only_active=True)

        if not tasks:
            st.info("まずは『タスク設定』ページでタスクを作ってみよう。")
        else:
            for task_id, name, point_value in tasks:
                cols = st.columns([3, 1])
                cols[0].write(f"{name} （{point_value} pt）")
                if cols[1].button("完了！", key=f"done_{task_id}"):
                    log_points(conn, task_id, point_value)
                    st.success(f"『{name}』を完了！ +{point_value} pt")

        total = get_total_points(conn)
        st.metric("いまの合計ポイント", f"{total} pt")

    # ===== 3) 履歴・合計ポイントを見る =====
    elif page == "履歴・合計ポイントを見る":
        st.header("📊 履歴・ポイント状況")

        total = get_total_points(conn)
        st.metric("いまの合計ポイント", f"{total} pt")

        st.subheader("最近の日記（直近10件）")
        diaries = get_recent_diaries(conn, limit=10)

        if not diaries:
            st.info("まだ日記がありません。『今日の日記を書く』から始めてみよう。")
        else:
            for entry_date, entry_time, mood, content, created_at in diaries:
                # ---- 時刻ラベル ----
                if entry_time:
                    time_label = entry_time[:5]  # "14:35:12" → "14:35"
                else:
                    time_label = created_at[11:16] if created_at else ""

                # ---- 日記本文の先頭5文字 ----
                snippet_source = (content or "").replace("\n", " ").strip()
                snippet = snippet_source[:5]

                # ---- タイトル ----
                if snippet:
                    title = f"{entry_date} {time_label} | {mood} | {snippet}"
                else:
                    title = f"{entry_date} {time_label} | {mood}"

                # ---- 展開エリア ----
                with st.expander(title):
                    st.write(content if content else "（本文なし）")
                    st.caption(f"保存日時: {created_at}")

    # ===== 4) タスク設定 =====
    elif page == "タスク設定":
        st.header("🛠 タスク設定（がんばりどころ・めんどいこと）")

        st.subheader("タスクを追加する")
        new_name = st.text_input("タスク名", placeholder="例：ブログを書く")
        new_point = st.number_input("ポイント", min_value=1, max_value=1000, value=10)

        if st.button("タスクを追加"):
            if new_name.strip():
                add_task(conn, new_name.strip(), int(new_point))
                st.success("タスクを追加したよ！")
            else:
                st.warning("タスク名を入力してね。")

        st.subheader("タスク一覧")
        all_tasks = get_tasks(conn, only_active=False)

        if not all_tasks:
            st.info("まだタスクがありません。上で作成してみよう。")
        else:
            for task_id, name, point_value, is_active in all_tasks:
                cols = st.columns([3, 1, 1])
                cols[0].write(f"{name} （{point_value} pt）")
                active_label = "有効" if is_active else "無効"
                cols[1].write(active_label)

                if is_active:
                    if cols[2].button("無効にする", key=f"deact_{task_id}"):
                        toggle_task_active(conn, task_id, False)
                        st.experimental_rerun()
                else:
                    if cols[2].button("有効にする", key=f"act_{task_id}"):
                        toggle_task_active(conn, task_id, True)
                        st.experimental_rerun()


if __name__ == "__main__":
    main()
