import google.generativeai as genai
import speech_recognition as sr
from pydub import AudioSegment
import os
from config import GEMINI_API_KEY

recognizer = sr.Recognizer()

# Ініціалізуємо Gemini
try:
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)

        models_to_try = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro']
        gemini_model = None

        for model_name in models_to_try:
            try:
                gemini_model = genai.GenerativeModel(model_name)
                test_response = gemini_model.generate_content("test")
                print(f"Gemini API налаштовано успішно з моделлю: {model_name}")
                break
            except Exception as model_error:
                print(f"Модель {model_name} недоступна: {model_error}")
                continue

        if not gemini_model:
            print("Не вдалося знайти робочу модель Gemini, використовується лише локальний парсинг")
    else:
        gemini_model = None
        print("GEMINI_API_KEY не знайдено, використовується лише локальний парсинг")
except Exception as e:
    print(f"Помилка налаштування Gemini API: {e}")
    gemini_model = None


# Функція для розпізнавання голосу
async def recognize_voice(audio_file_path):
    """Розпізнає голос з аудіофайлу та повертає текст"""
    try:
        # Конвертуємо OGG у WAV
        audio = AudioSegment.from_ogg(audio_file_path)
        wav_path = audio_file_path.replace('.ogg', '.wav')
        audio.export(wav_path, format="wav")

        # Розпізнаємо голос
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)

        # Спробуємо різні сервіси розпізнавання
        try:
            text = recognizer.recognize_google(audio_data, language='uk-UA')
            print(f"Google Speech Recognition результат: {text}")
            return text
        except sr.UnknownValueError:
            try:
                # Спробуємо з російською мовою як резерв
                text = recognizer.recognize_google(audio_data, language='ru-RU')
                print(f"Google Speech Recognition (ru) результат: {text}")
                return text
            except sr.UnknownValueError:
                try:
                    # Спробуємо з англійською як останній резерв
                    text = recognizer.recognize_google(audio_data, language='en-US')
                    print(f"Google Speech Recognition (en) результат: {text}")
                    return text
                except sr.UnknownValueError:
                    return None
        except sr.RequestError as e:
            print(f"Помилка сервісу розпізнавання: {e}")
            return None

    except Exception as e:
        print(f"Помилка розпізнавання голосу: {e}")
        return None
    finally:
        try:
            if os.path.exists(audio_file_path):
                os.remove(audio_file_path)
            if 'wav_path' in locals() and os.path.exists(wav_path):
                os.remove(wav_path)
        except Exception as cleanup_error:
            print(f"Помилка при видаленні тимчасових файлів: {cleanup_error}")