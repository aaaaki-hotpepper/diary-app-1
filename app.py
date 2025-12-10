import streamlit as st
import sqlite3
import datetime
import pytz

# ===== タイムゾーン（日本時間） =====
JST = pytz.timezone("Asia/Tokyo")


# ===== DB 接続 & 初期化 =====
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
            entry_time TEXT,
            mood TEXT,
            content TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # タスクテーブル（がんばったこと・めんどいこと）
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            point_value INTEGER NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        )
    """)

    # ポイントログ
    cur.execute("""
        CREATE TABLE IF NOT EXISTS points_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            points INTEGER NOT NULL,
            done_at TEXT NOT NULL
        )
    """)

    conn.commit()


# ===== 共通で使う「今の日本時間」 =====
def now_jst():
    return datetime.datetime.now(JST)


# ===== DB 操作用関数 =====
def save_diary(conn, entry_date, entry_time, mood, content):
    """日記を毎回「新規」で保存する"""
    cur = conn.cursor()

    # entry_date は date_input から来るので str に変換
    date_str = entry_date.isoformat()

    # entry_time は time_input（None になる可能性もある）
    if entry_time:
        time_str = entry_time.strftime("%H:%M")
    else:
        time_str = None

    created_at = now_jst().isoformat(timespec="seconds")

    cur.execute(
        """
        INSERT INTO diary_entries (entry_date, entry_time, mood, content, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (date_str, time_str, mood, content, created_at),
    )
    conn.commit()


def get_recent_diaries(conn, limit=10):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT entry_date, entry_time, mood, content, created_at
        FROM diary_entries
        ORDER BY datetime(created_at) DESC
        LIMIT ?
        """,
        (limit,),
    )
    return cur.fetchall()


def get_total_points(conn):
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(points), 0) FROM points_log")
    (total,) = cur.fetchone()
    return total


def get_tasks(conn, only_active=True):
    cur = conn.cursor()
    if only_active:
        cur.execute("SELECT id, name, point_value FROM tasks WHERE is_active = 1")
    else:
        cur.execute(
            "SELECT id, name, point_value, is_active FROM tasks ORDER BY id ASC"
        )
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
    now = now_jst().isoformat(timespec="seconds")
    cur.execute(
        "INSERT INTO points_log (task_id, points, done_at) VALUES (?, ?, ?)",
        (task_id, points, now),
    )
    conn.commit()


# ===== Streamlit アプリ本体 =====
def main():
    st.set_page_config(page_title="日記 & ごほうびポイント", page_icon="📔")

    conn = get_connection()
    init_db(conn)

    st.title("📔 日記 & がんばりポイント")

    menu = [
        "今日の日記を書く",
        "ポイントを貯める",
        "履歴・合計ポイントを見る",
        "タスク設定",
    ]
    page = st.sidebar.radio("メニュー", menu)

    # -------------------------
    # 1) 今日の日記を書く
    # -------------------------
    if page == "今日の日記を書く":
        st.header("📝 今日の日記を書く")

        today = now_jst().date()
        now_time = now_jst().time().replace(second=0, microsecond=0)

        entry_date = st.date_input("日付", value=today)
        entry_time = st.time_input("時間（任意）", value=now_time)
        mood = st.selectbox("今日の気分", ["💯 超最高", "😀 いい感じ", "☺️ おつかれ", "💢 イラ", "😕 いまいち", "😭 つらい", "無"])
        content = st.text_area("今日あったこと・感じたこと", height=200)

        if st.button("この内容で保存する"):
            if not content.strip():
                st.warning("本文が空です。なにか一言でも書いてみよう！")
            else:
                save_diary(conn, entry_date, entry_time, mood, content)
                st.success("日記を保存しました！")

    # -------------------------
    # 2) ポイントを貯める
    # -------------------------
    elif page == "ポイントを貯める":
        st.header("⭐ ポイントを貯める")

        tasks = get_tasks(conn, only_active=True)
        if not tasks:
            st.info("まだタスクが登録されていません。「タスク設定」から追加できます。")
        else:
            for task_id, name, point_value in tasks:
                cols = st.columns([3, 1])
                cols[0].write(f"{name}  (+{point_value} pt)")
                if cols[1].button("やった！", key=f"task_{task_id}"):
                    log_points(conn, task_id, point_value)
                    st.success(f"「{name}」のポイントを記録しました！")

        st.write("---")
        total = get_total_points(conn)
        st.metric("いまの合計ポイント", f"{total} pt")

    # -------------------------
    # 3) 履歴・合計ポイントを見る
    # -------------------------
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
            # ---- 時刻の表示ロジック ----
            if entry_time:
                time_label = entry_time[:5]  # 例: "14:35:12" → "14:35"
            else:
                # entry_time がない（古いデータ）の場合は created_at から取得
                time_label = created_at[11:16] if created_at else ""

            # ---- 日記本文の先頭5文字をタイトルに入れる ----
            snippet_source = (content or "").replace("\n", " ").strip()
            snippet = snippet_source[:5]  # 先頭5文字だけ取り出す

            # ---- タイトル（見出し）----
            if snippet:
                title = f"{entry_date} {time_label} | {mood} | {snippet}"
            else:
                title = f"{entry_date} {time_label} | {mood}"

            # ---- 展開エリア ----
            with st.expander(title):
                st.write(content if content else "（本文なし）")
                st.caption(f"保存日時: {created_at}")

    
    # 4) タスク設定
    # -------------------------
    elif page == "タスク設定":
        st.header("🛠 タスク設定（がんばり & めんどいこと）")

        st.subheader("タスクを追加")
        new_name = st.text_input("タスク名（例：筋トレ10分、めんどいメール返信 など）")
        new_points = st.number_input("ポイント数", min_value=1, max_value=100, value=5)

        if st.button("タスクを追加"):
            if not new_name.strip():
                st.warning("タスク名を入力してください。")
            else:
                add_task(conn, new_name.strip(), int(new_points))
                st.success("タスクを追加しました！")

        st.write("---")
        st.subheader("タスク一覧")

        all_tasks = get_tasks(conn, only_active=False)
        if not all_tasks:
            st.info("まだタスクがありません。")
        else:
            for task_id, name, point_value, is_active in all_tasks:
                status = "✅ 有効" if is_active else "🚫 無効"
                st.write(f"- {name} (+{point_value} pt)  {status}")


if __name__ == "__main__":
    main()
