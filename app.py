import streamlit as st
import sqlite3
from datetime import datetime, date
import pytz

# ===== タイムゾーン（日本時間） =====
JST = pytz.timezone("Asia/Tokyo")

# ===== 気分リスト（絵文字付き表示用） =====
MOOD_OPTIONS = [
    ("超最高", "😆"),
    ("いい感じ", "😊"),
    ("まあまあ", "🙂"),
    ("いまいち", "😕"),
    ("最悪", "😫"),
    ("なし", "⚪️"),
]

MOOD_LABELS = [f"{emoji} {text}" for (text, emoji) in MOOD_OPTIONS]
MOOD_TO_EMOJI = {text: emoji for (text, emoji) in MOOD_OPTIONS}
LABEL_TO_MOOD = {label: text for (text, emoji), label in zip(MOOD_OPTIONS, MOOD_LABELS)}


# ===== DB 接続まわり =====
@st.cache_resource
def get_connection():
    # Streamlit Cloud でもローカルでも同じファイル名を使う
    conn = sqlite3.connect("diary_points.db", check_same_thread=False)
    return conn


def init_db(conn):
    cur = conn.cursor()

    # 日記テーブル
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

    # タスクテーブル（ポイントを貯める用）
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

    # ポイント履歴テーブル（貯める＆使う両方）
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS points_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_type TEXT NOT NULL,       -- "earn" or "spend"
            task_or_reason TEXT NOT NULL,    -- 何の項目か
            points INTEGER NOT NULL,         -- 加算はプラス、消費はマイナス
            note TEXT,                       -- コメント / メモ
            created_at TEXT NOT NULL
        )
        """
    )

    # デフォルトタスクを少しだけ入れておく（空のときだけ）
    cur.execute("SELECT COUNT(*) FROM tasks")
    if cur.fetchone()[0] == 0:
        default_tasks = [
            ("日記を書いた", 1),
            ("Python の勉強", 3),
            ("運動した", 3),
            ("早起きできた", 2),
        ]
        cur.executemany(
            "INSERT INTO tasks (name, point_value, is_active) VALUES (?, ?, 1)",
            default_tasks,
        )

    conn.commit()


# ===== 日記関連の関数 =====
def save_diary(conn, entry_date: date, entry_time, mood: str, content: str):
    now_jst = datetime.now(JST).isoformat(timespec="seconds")
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO diary_entries (entry_date, entry_time, mood, content, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            entry_date.isoformat(),
            entry_time.strftime("%H:%M:%S") if entry_time else None,
            mood,
            content,
            now_jst,
        ),
    )
    conn.commit()


def get_recent_diaries(conn, limit: int = 10):
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


# ===== ポイント関連の関数 =====
def log_points(conn, action_type: str, task_or_reason: str, points: int, note: str):
    """ポイントの加算・消費を記録"""
    now_jst = datetime.now(JST).isoformat(timespec="seconds")
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO points_log (action_type, task_or_reason, points, note, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (action_type, task_or_reason, points, note, now_jst),
    )
    conn.commit()


def get_total_points(conn) -> int:
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(points), 0) FROM points_log")
    total = cur.fetchone()[0]
    return total or 0


def get_points_history(conn, limit: int | None = None):
    cur = conn.cursor()
    base_sql = """
        SELECT action_type, task_or_reason, points, note, created_at
        FROM points_log
        ORDER BY datetime(created_at) DESC
    """
    if limit is not None:
        base_sql += " LIMIT ?"
        cur.execute(base_sql, (limit,))
    else:
        cur.execute(base_sql)
    return cur.fetchall()


def get_active_tasks(conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, name, point_value
        FROM tasks
        WHERE is_active = 1
        ORDER BY id
        """
    )
    return cur.fetchall()


def get_all_tasks(conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, name, point_value, is_active
        FROM tasks
        ORDER BY id
        """
    )
    return cur.fetchall()


def add_task(conn, name: str, point_value: int):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO tasks (name, point_value, is_active) VALUES (?, ?, 1)",
        (name, point_value),
    )
    conn.commit()


def update_task_active(conn, task_id: int, is_active: bool):
    cur = conn.cursor()
    cur.execute(
        "UPDATE tasks SET is_active = ? WHERE id = ?",
        (1 if is_active else 0, task_id),
    )
    conn.commit()


# ===== メイン処理 =====
def main():
    st.set_page_config(page_title="日記 & ごほうびポイント", layout="wide")

    conn = get_connection()
    init_db(conn)

    # ---- サイドバー ----
    st.sidebar.title("メニュー")
    page = st.sidebar.radio(
        "ページを選んでください",
        (
            "今日の日記を書く",
            "ポイントを貯める",
            "ポイントを使う",
            "履歴・合計ポイントを見る",
            "タスク設定",
        ),
    )

    # 共通で残高を出しておく
    total_points = get_total_points(conn)

    # ===== 1) 今日の日記を書く =====
    if page == "今日の日記を書く":
        st.header("📔 今日の日記を書く")

        now = datetime.now(JST)
        entry_date = st.date_input("日付", value=now.date())
        entry_time = st.time_input("書いた時間", value=now.time().replace(microsecond=0))

        mood_label = st.selectbox("今日の気分", MOOD_LABELS, index=1)
        mood_text = LABEL_TO_MOOD[mood_label]

        content = st.text_area("今日の出来事や気づき", height=200)

        if st.button("この内容で保存する"):
            if not content.strip() and mood_text == "なし":
                st.warning("なにか一言でも良いので、本文か気分を入力してね。")
            else:
                save_diary(conn, entry_date, entry_time, mood_text, content)
                st.success("日記を保存しました！")

        st.caption("※ 保存すると毎回あたらしい日記として追加されます（上書きではありません）。")

    # ===== 2) ポイントを貯める =====
    elif page == "ポイントを貯める":
        st.header("🌱 ポイントを貯める")
        st.metric("現在のポイント残高", f"{total_points} pt")

        tasks = get_active_tasks(conn)
        if not tasks:
            st.info("アクティブなタスクがありません。「タスク設定」から追加してください。")
        else:
            task_names = [t[1] for t in tasks]
            task_choice = st.selectbox("どの項目でポイントを貯める？", task_names)

            # 選ばれたタスクのデフォルトポイント
            selected_task = next(t for t in tasks if t[1] == task_choice)
            default_point = selected_task[2]

            points = st.number_input(
                "今回貯めるポイント", min_value=1, step=1, value=default_point
            )
            note = st.text_input("メモ（任意：どんな行動をしたかなど）")

            if st.button("ポイントを追加"):
                log_points(conn, "earn", task_choice, int(points), note)
                st.success(f"{points} pt を追加しました！")
                st.experimental_rerun()

    # ===== 3) ポイントを使う =====
    elif page == "ポイントを使う":
        st.header("🎁 ポイントを使う（ご褒美）")
        st.metric("現在のポイント残高", f"{total_points} pt")

        reason = st.text_input("ポイントを使う理由（例：ご褒美ビール、外食、コスメ）")
        use_points = st.number_input(
            "使うポイント数", min_value=1, step=1, value=1, help="残高の範囲内で入力してください。"
        )
        note = st.text_input("メモ（任意：どんなご褒美かなど）")

        if st.button("ポイントを消費する"):
            if use_points > total_points:
                st.error("ポイント残高が足りません…😢")
            else:
                label = reason.strip() or "理由なし"
                log_points(conn, "spend", label, -int(use_points), note)
                st.success(f"{use_points} pt を消費しました！（ご褒美：{label}）")
                st.experimental_rerun()

    # ===== 4) 履歴・合計ポイントを見る =====
    elif page == "履歴・合計ポイントを見る":
        st.header("📊 履歴・合計ポイントを見る")

        st.metric("いまの合計ポイント", f"{total_points} pt")

        # ---- 最近の日記（直近 10 件） ----
        st.subheader("📝 最近の日記（直近10件）")
        diaries = get_recent_diaries(conn, limit=10)

        if not diaries:
            st.info("まだ日記がありません。「今日の日記を書く」から始めてみよう。")
        else:
            for entry_date, entry_time, mood_text, content, created_at in diaries:
                # 時刻ラベル
                if entry_time:
                    time_label = entry_time[:5]  # "HH:MM:SS" → "HH:MM"
                else:
                    time_label = created_at[11:16] if created_at else ""

                # 気分ラベル（絵文字付き）
                emoji = MOOD_TO_EMOJI.get(mood_text, "")
                if mood_text == "なし":
                    mood_label = f"{emoji} 気分記録なし"
                else:
                    mood_label = f"{emoji} {mood_text}"

                # 本文先頭 20 文字をタイトルに入れる
                snippet_source = (content or "").replace("\n", " ").strip()
                snippet = snippet_source[:20]

                title = f"{entry_date} {time_label} | {mood_label}"
                if snippet:
                    title += f" | {snippet}"

                with st.expander(title):
                    st.write(content if content else "（本文なし）")
                    st.caption(f"保存日時: {created_at}")

        # ---- ポイント履歴 ----
        st.subheader("📚 ポイント履歴")
        history = get_points_history(conn)

        if not history:
            st.info("まだポイント履歴がありません。")
        else:
            # 表示用に加工
            rows = []
            running_total = 0
            # 履歴は新しい順なので、表示用残高は計算だけにする or 別にする
            # ここではシンプルに「プラス / マイナス」だけ表示
            for action_type, task_or_reason, points, note, created_at in history:
                kind = "貯めた" if action_type == "earn" else "使った"
                rows.append(
                    {
                        "日時": created_at,
                        "種類": kind,
                        "項目 / 理由": task_or_reason,
                        "ポイント": points,
                        "メモ": note or "",
                    }
                )

            import pandas as pd  # Streamlit には同梱されているので requirements 追加は不要

            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True)

    # ===== 5) タスク設定 =====
    elif page == "タスク設定":
        st.header("🛠 タスク設定（ポイントを貯める項目）")

        st.write("ポイントを貯めるときに選べる『タスク』を管理します。")

        # 既存タスク一覧
        all_tasks = get_all_tasks(conn)
        if not all_tasks:
            st.info("まだタスクがありません。下のフォームから追加してください。")
        else:
            st.subheader("現在のタスク一覧")
            for task_id, name, point_value, is_active in all_tasks:
                col1, col2, col3 = st.columns([4, 2, 2])
                with col1:
                    st.write(name)
                with col2:
                    st.write(f"{point_value} pt")
                with col3:
                    active_label = "✅ 有効" if is_active else "⛔ 無効"
                    if st.button(
                        active_label + f"（切り替え）", key=f"toggle_{task_id}"
                    ):
                        update_task_active(conn, task_id, not bool(is_active))
                        st.experimental_rerun()

        st.subheader("タスクを追加する")
        new_name = st.text_input("タスク名（例：勉強1時間、掃除30分 など）")
        new_point = st.number_input(
            "獲得ポイント", min_value=1, step=1, value=1, key="new_task_point"
        )

        if st.button("タスクを追加"):
            if not new_name.strip():
                st.warning("タスク名を入力してください。")
            else:
                add_task(conn, new_name.strip(), int(new_point))
                st.success("タスクを追加しました！")
                st.experimental_rerun()


if __name__ == "__main__":
    main()
