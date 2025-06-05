from aiogram import Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram import F
from database import get_active_session, get_or_create_exercise_id, close_active_session
from utils import parse_exercise, format_exercise_summary
from services import recognize_voice
from datetime import datetime
from config import bot, storage, TELEGRAM_TOKEN
import sqlite3
import aiohttp
import aiofiles
import os
import tempfile

dp = Dispatcher(storage=storage)


class WorkoutState(StatesGroup):
    ACTIVE = State()


@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    # Скидаємо стан при /start
    await state.clear()
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="Старт"), types.KeyboardButton(text="Стоп")]],
        resize_keyboard=True
    )
    await message.answer("Вітаю! Це бот для фіксації тренувань. Натисніть 'Старт', щоб почати.", reply_markup=keyboard)


@dp.message(F.text == "Старт")
async def start_workout(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    current_state = await state.get_state()

    # Перевіряємо стан FSM, а не лише базу даних
    if current_state == WorkoutState.ACTIVE.state:
        await message.answer("Тренування вже активне. Надсилайте вправи або натисніть Стоп, щоб завершити.")
        return

    # Закриваємо будь-яку активну сесію в БД (на випадок збою)
    close_active_session(user_id)

    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()
    c.execute("INSERT INTO training_sessions (user_id, started_at) VALUES (?, ?)",
              (user_id, datetime.now()))
    session_id = c.lastrowid
    conn.commit()
    conn.close()

    await state.set_state(WorkoutState.ACTIVE)
    await state.update_data(session_id=session_id)
    await message.answer(
        "Тренування розпочато! Надсилайте вправи у форматі:\n"
        "• 'Зробив 20 відтискань'\n"
        "• 'Присідання 30 разів з вагою 20 кг'\n"
        "• '15 підтягувань'\n"
        "• 'Жим лежачи 12 повторів з вагою 80 кг'\n\n"
        "Також можете надсилати голосові повідомлення! 🎤"
    )


@dp.message(F.text == "Стоп")
async def stop_workout(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    current_state = await state.get_state()

    if current_state != WorkoutState.ACTIVE.state:
        await message.answer("Ви ще не почали тренування. Натисніть 'Старт', щоб почати.")
        return

    session_id = get_active_session(user_id)
    if not session_id:
        await message.answer("Сесію вже завершено. Натисніть 'Старт', щоб почати нову.")
        await state.clear()
        return

    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()
    c.execute("UPDATE training_sessions SET ended_at = ? WHERE id = ?",
              (datetime.now(), session_id))

    # Отримуємо всі записи вправ (без групування в SQL)
    c.execute('''SELECT e.name, ee.reps, ee.weight
                 FROM exercise_entries ee
                 JOIN exercises e ON ee.exercise_id = e.id
                 WHERE ee.session_id = ?
                 ORDER BY e.name, ee.timestamp''', (session_id,))
    exercises = c.fetchall()
    conn.commit()
    conn.close()

    if not exercises:
        await message.answer("Тренування завершено! Ви не додали жодної вправи.")
    else:
        summary = "Тренування завершено! Ви зробили:\n"
        formatted_exercises = format_exercise_summary(exercises)
        summary += "\n".join(formatted_exercises)
        await message.answer(summary)

    await state.clear()


@dp.message(Command("last"))
async def cmd_last(message: types.Message):
    user_id = message.from_user.id
    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()
    c.execute(
        "SELECT id, started_at FROM training_sessions WHERE user_id = ? AND ended_at IS NOT NULL ORDER BY ended_at DESC LIMIT 1",
        (user_id,))
    session = c.fetchone()
    if not session:
        await message.answer("Ви ще не маєте завершених тренувань.\nНатисніть 'Старт', щоб почати перше тренування.")
        conn.close()
        return

    c.execute('''SELECT e.name, ee.reps, ee.weight
                 FROM exercise_entries ee
                 JOIN exercises e ON ee.exercise_id = e.id
                 WHERE ee.session_id = ?
                 ORDER BY e.name, ee.timestamp''', (session[0],))
    exercises = c.fetchall()
    conn.close()

    if not exercises:
        await message.answer("Останнє тренування не містить вправ.")
    else:
        session_date = datetime.fromisoformat(session[1]).strftime("%d.%m.%Y %H:%M")
        summary = f"📊 Останнє тренування ({session_date}):\n"
        formatted_exercises = format_exercise_summary(exercises)
        summary += "\n".join(formatted_exercises)
        await message.answer(summary)


def get_approach_word(count):
    """Возвращает правильную форму слова 'підхід' в зависимости от количества"""
    if count % 10 == 1 and count % 100 != 11:
        return "підхід"
    elif count % 10 in [2, 3, 4] and count % 100 not in [12, 13, 14]:
        return "підходи"
    else:
        return "підходів"

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    user_id = message.from_user.id
    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM training_sessions WHERE user_id = ? AND ended_at IS NOT NULL", (user_id,))
    session_count = c.fetchone()[0]

    c.execute(
        "SELECT COUNT(*) FROM exercise_entries WHERE session_id IN (SELECT id FROM training_sessions WHERE user_id = ?)",
        (user_id,))
    exercise_count = c.fetchone()[0]

    c.execute('''SELECT e.name, COUNT(*) as count, SUM(ee.reps) as total_reps
                 FROM exercise_entries ee
                 JOIN exercises e ON ee.exercise_id = e.id
                 WHERE ee.session_id IN (SELECT id FROM training_sessions WHERE user_id = ?)
                 GROUP BY e.name
                 ORDER BY count DESC
                 LIMIT 3''', (user_id,))
    top_exercises = c.fetchall()

    conn.close()

    if session_count == 0:
        await message.answer("Ви ще не маєте завершених тренувань.\nНатисніть 'Старт', щоб почати перше тренування.")
        return

    response = f"📈 Статистика:\n"
    response += f"🏋️ Кількість тренувань: {session_count}\n"
    response += f"💪 Загальна кількість вправ: {exercise_count}\n\n"

    if top_exercises:
        response += "🏆 Топ-3 вправи:\n"
        for i, (name, count, total_reps) in enumerate(top_exercises, 1):
            approach_word = get_approach_word(count)
            response += f"{i}. {name}: {total_reps} повторів ({count} {approach_word})\n"

    await message.answer(response)


@dp.message(F.voice)
async def process_voice_message(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    current_state = await state.get_state()

    if current_state != WorkoutState.ACTIVE.state:
        await message.answer("Щоб надсилати вправи, спершу натисніть кнопку Старт")
        return

    session_id = get_active_session(user_id)
    if not session_id:
        await message.answer("Щоб надсилати вправи, спершу натисніть кнопку Старт")
        await state.clear()
        return

    try:
        processing_message = await message.answer("🎤 Обробляю голосове повідомлення...")

        voice_file = await bot.get_file(message.voice.file_id)

        temp_dir = tempfile.gettempdir()
        temp_file_path = os.path.join(temp_dir, f"voice_{message.voice.file_id}.ogg")

        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{voice_file.file_path}") as resp:
                async with aiofiles.open(temp_file_path, 'wb') as f:
                    async for chunk in resp.content.iter_chunked(1024):
                        await f.write(chunk)

        recognized_text = await recognize_voice(temp_file_path)

        await processing_message.delete()

        if not recognized_text:
            await message.answer(
                "Не вдалося розпізнати голосове повідомлення.\nСпробуйте ще раз або надішліть текстом.")
            return

        await message.answer(f"🎯 Розпізнано: \"{recognized_text}\"")

        exercise_data = parse_exercise(recognized_text)
        if not exercise_data or 'name' not in exercise_data or 'reps' not in exercise_data:
            await message.answer(
                "Повідомлення не схоже на опис вправи.\n"
                "Надішліть у форматі:\n"
                "• 'Зробив 15 підтягувань'\n"
                "• 'Відтискання 20 разів'\n"
                "• 'Присідання 30 разів з вагою 20 кг'"
            )
            return

        exercise_id = get_or_create_exercise_id(exercise_data['name'])
        conn = sqlite3.connect("workouts.db")
        c = conn.cursor()
        c.execute(
            "INSERT INTO exercise_entries (session_id, exercise_id, reps, weight, timestamp) VALUES (?, ?, ?, ?, ?)",
            (session_id, exercise_id, exercise_data['reps'], exercise_data.get('weight'), datetime.now()))
        conn.commit()
        conn.close()

        await message.answer(f"✅ Записано: {exercise_data['name']} – {exercise_data['reps']} повторів" +
                             (f" з вагою {exercise_data['weight']} кг" if exercise_data.get('weight') else ""))

    except Exception as e:
        print(f"Помилка обробки голосового повідомлення: {e}")
        await message.answer("Не вдалося розпізнати голосове повідомлення.\nСпробуйте ще раз або надішліть текстом.")


@dp.message(WorkoutState.ACTIVE, F.text & ~F.text.in_(["Старт", "Стоп"]))
async def process_exercise_text(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    session_id = get_active_session(user_id)

    if not session_id:
        await message.answer("Щоб надсилати вправи, спершу натисніть кнопку Старт")
        await state.clear()  # Скидаємо стан якщо сесії немає
        return

    exercise_data = parse_exercise(message.text)
    if not exercise_data or 'name' not in exercise_data or 'reps' not in exercise_data:
        await message.answer(
            "Повідомлення не схоже на опис вправи.\n"
            "Надішліть у форматі:\n"
            "• 'Зробив 15 підтягувань'\n"
            "• 'Відтискання 20 разів'\n"
            "• 'Присідання 30 разів з вагою 20 кг'"
        )
        return

    exercise_id = get_or_create_exercise_id(exercise_data['name'])
    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()
    c.execute("INSERT INTO exercise_entries (session_id, exercise_id, reps, weight, timestamp) VALUES (?, ?, ?, ?, ?)",
              (session_id, exercise_id, exercise_data['reps'], exercise_data.get('weight'), datetime.now()))
    conn.commit()
    conn.close()

    await message.answer(f"✅ Записано: {exercise_data['name']} – {exercise_data['reps']} повторів" +
                         (f" з вагою {exercise_data['weight']} кг" if exercise_data.get('weight') else ""))


@dp.message(F.text & ~F.text.in_(["Старт", "Стоп"]))
async def handle_unknown_text(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state != WorkoutState.ACTIVE.state:
        await message.answer("Щоб розпочати тренування, натисніть кнопку 'Старт' 🏋️")