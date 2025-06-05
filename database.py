import sqlite3
from datetime import datetime

def init_db():
    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS training_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        started_at DATETIME NOT NULL,
        ended_at DATETIME
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS exercises (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS exercise_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        exercise_id INTEGER NOT NULL,
        reps INTEGER NOT NULL,
        weight INTEGER,
        timestamp DATETIME NOT NULL,
        FOREIGN KEY (session_id) REFERENCES training_sessions(id),
        FOREIGN KEY (exercise_id) REFERENCES exercises(id)
    )''')
    conn.commit()
    conn.close()


init_db()


def get_or_create_exercise_id(name):
    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()
    c.execute("SELECT id FROM exercises WHERE name = ?", (name,))
    result = c.fetchone()
    if result:
        exercise_id = result[0]
    else:
        c.execute("INSERT INTO exercises (name) VALUES (?)", (name,))
        exercise_id = c.lastrowid
    conn.commit()
    conn.close()
    return exercise_id


def get_active_session(user_id):
    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()
    c.execute("SELECT id FROM training_sessions WHERE user_id = ? AND ended_at IS NULL", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None


def close_active_session(user_id):
    """Закрити активну сесію якщо вона є"""
    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()
    c.execute("UPDATE training_sessions SET ended_at = ? WHERE user_id = ? AND ended_at IS NULL",
              (datetime.now(), user_id))
    conn.commit()
    conn.close()