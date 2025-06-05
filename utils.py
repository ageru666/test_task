import json
import re
from services import gemini_model

def parse_exercise(text):
    try:
        if gemini_model:
            prompt = f"""
Ти помічник для парсингу описів вправ. Текст може містити помилки розпізнавання мовлення.

КРИТИЧНО ВАЖЛИВО: 
- Якщо текст НЕ схожий на опис вправи - поверни {{"error": "not_exercise"}}
- Виправляй помилки ТІЛЬКИ коли впевнений, що це опис вправи
- ЗБЕРІГАЙ ПОВНУ НАЗВУ ВПРАВИ! Не скорочуй і не спрощуй назви!
- Не перетворюй випадкові слова на вправи!

ЗАВДАННЯ: Проаналізуй текст і поверни JSON:
1. Якщо це НЕ схоже на вправу → {{"error": "not_exercise"}}
2. Якщо це вправа → {{"name": "ПОВНА_назва_вправи", "reps": число, "weight": число_або_null}}

ВАЖЛИВІ ПРАВИЛА ДЛЯ НАЗВ:
- "французький жим лежачи" → "французький жим лежачи" (НЕ просто "жим лежачи"!)
- "жим штанги лежачи" → "жим штанги лежачи" 
- "жим гантель лежачи" → "жим гантель лежачи"
- "присідання з штангою" → "присідання з штангою"
- "підтягування широким хватом" → "підтягування широким хватом"
- "віджимання від підлоги" → "віджимання від підлоги"
- "планка на ліктях" → "планка на ліктях"

ПОМИЛКИ РОЗПІЗНАВАННЯ які потрібно виправляти:
- "приїде", "приїду", "приїдь" + число + "раз" → "присідання" 
- "відтискань я", "відтискання я" → "відтискання"
- "підтягуван я", "підтягув я" → "підтягування"
- "планк а", "планка" → "планка"

НЕ ВИПРАВЛЯЙ якщо:
- Слово не схоже на назву вправи (банан, музика, привіт, тощо)
- Немає числа що може бути повтореннями
- Загальний контекст не про фітнес

ПРИКЛАДИ ПРАВИЛЬНОЇ РОБОТИ:
"французький жим лежачи 12 повторів з вагою 40 кг" → {{"name": "французький жим лежачи", "reps": 12, "weight": 40}}
"жим штанги лежачи 10 разів 80 кг" → {{"name": "жим штанги лежачи", "reps": 10, "weight": 80}}
"присідання з штангою 15 повторів" → {{"name": "присідання з штангою", "reps": 15, "weight": null}}
"підтягування широким хватом 8 разів" → {{"name": "підтягування широким хватом", "reps": 8, "weight": null}}
"приїде 20 разів" → {{"name": "присідання", "reps": 20, "weight": null}}
"відтискань я 15" → {{"name": "відтискання", "reps": 15, "weight": null}}
"банан 20 разів" → {{"error": "not_exercise"}}
"музика грає" → {{"error": "not_exercise"}}

ВХІДНИЙ ТЕКСТ: "{text}"

Поверни ЛИШЕ JSON, без додаткового тексту.
            """

            response = gemini_model.generate_content(prompt)
            response_text = response.text.strip()

            response_text = response_text.replace('```json', '').replace('```', '').strip()

            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1

            if json_start != -1 and json_end > json_start:
                json_text = response_text[json_start:json_end]
                result = json.loads(json_text)

                if result.get('error') == 'not_exercise':
                    print(f"Gemini визначив що '{text}' не є вправою")
                    return None

                if 'name' in result and 'reps' in result and isinstance(result['reps'], int):
                    print(f"Gemini успішно розпарсив: '{text}' → {result}")
                    return result
                else:
                    print(f"Gemini повернув некоректний JSON: {result}")
            else:
                print(f"Не знайдено JSON у відповіді Gemini: {response_text}")

    except Exception as e:
        print(f"Помилка парсингу через Gemini: {e}")
        if 'response' in locals():
            print(f"Відповідь від Gemini: {response.text}")

    # Локальний парсинг як fallback
    print("Використовуємо локальний парсинг як резерв")
    return smart_local_parse(text)


def smart_local_parse(text):
    """Розумний локальний парсинг з збереженням повних назв вправ"""
    try:
        text_lower = text.lower().strip()
        original_text = text.strip()

        if not re.search(r'\d+', text_lower):
            return None

        reps = None
        weight = None

        reps_patterns = [
            r'(\d+)\s*(?:повтор|раз|rep)',
            r'(?:повтор|раз|rep)\w*\s*(\d+)',
            r'(\d+)\s*(?=\s|$)',
        ]

        for pattern in reps_patterns:
            match = re.search(pattern, text_lower)
            if match:
                reps = int(match.group(1))
                break

        weight_patterns = [
            r'(\d+)\s*кг',
            r'з\s*вагою\s*(\d+)',
            r'вага\s*(\d+)',
        ]

        for pattern in weight_patterns:
            match = re.search(pattern, text_lower)
            if match:
                weight = int(match.group(1))
                break

        if not reps:
            return None

        exercise_name = extract_exercise_name(original_text, text_lower)

        if not exercise_name:
            return None

        return {
            "name": exercise_name,
            "reps": reps,
            "weight": weight
        }

    except Exception as e:
        print(f"Помилка розумного локального парсингу: {e}")
        return None


def extract_exercise_name(original_text, text_lower):
    """Витягує повну назву вправи зі збереженням деталей"""

    corrections = {
        'приїде': 'присідання',
        'приїду': 'присідання',
        'приїдь': 'присідання',
        'відтискань я': 'відтискання',
        'відтискання я': 'відтискання',
        'підтягуван я': 'підтягування',
        'підтягув я': 'підтягування',
        'планк а': 'планка',
    }

    corrected_text = text_lower
    for wrong, correct in corrections.items():
        if wrong in corrected_text:
            corrected_text = corrected_text.replace(wrong, correct)

    exercise_patterns = [
        (r'французьк\w*\s+жим(?:\s+лежачи)?', 'французький жим лежачи'),

        (r'жим\s+штанги\s+лежачи', 'жим штанги лежачи'),
        (r'жим\s+гантел[ьі]\s+лежачи', 'жим гантель лежачи'),
        (r'жим\s+лежачи', 'жим лежачи'),
        (r'жим\s+стоячи', 'жим стоячи'),
        (r'жим(?:\s+від)?\s+грудей', 'жим від грудей'),

        (r'присідання\s+з\s+штангою', 'присідання з штангою'),
        (r'присідання\s+з\s+гантел[ьі]', 'присідання з гантеллю'),
        (r'присідання', 'присідання'),

        (r'підтягування\s+широким\s+хватом', 'підтягування широким хватом'),
        (r'підтягування\s+вузьким\s+хватом', 'підтягування вузьким хватом'),
        (r'підтягування\s+зворотним\s+хватом', 'підтягування зворотним хватом'),
        (r'підтягування', 'підтягування'),

        (r'(?:відтискання|віджимання)\s+від\s+підлоги', 'відтискання від підлоги'),
        (r'(?:відтискання|віджимання)\s+на\s+брусах', 'відтискання на брусах'),
        (r'(?:відтискання|віджимання)', 'відтискання'),

        (r'планка\s+на\s+ліктях', 'планка на ліктях'),
        (r'планка\s+на\s+руках', 'планка на руках'),
        (r'планка', 'планка'),

        (r'тяга\s+штанги\s+в\s+нахилі', 'тяга штанги в нахилі'),
        (r'тяга\s+гантел[ьі]\s+в\s+нахилі', 'тяга гантель в нахилі'),
        (r'тяга\s+верхнього\s+блоку', 'тяга верхнього блоку'),

        (r'махи\s+гантел[ьі]', 'махи гантелями'),
        (r'розведення\s+гантел[ьі]\s+лежачи', 'розведення гантель лежачи'),
        (r'розведення\s+гантел[ьі]', 'розведення гантель'),

        (r'випади\s+з\s+гантел[ьі]', 'випади з гантелями'),
        (r'випади', 'випади'),
        (r'скручування', 'скручування'),
    ]

    for pattern, name in exercise_patterns:
        if re.search(pattern, corrected_text):
            return name

    basic_exercises = ['жим', 'присідання', 'підтягування', 'відтискання', 'віджимання', 'планка', 'тяга']

    for exercise in basic_exercises:
        if exercise in corrected_text:
            words = original_text.split()
            exercise_words = []
            found = False

            for i, word in enumerate(words):
                if exercise in word.lower():
                    start_idx = max(0, i - 2)
                    end_idx = min(len(words), i + 3)
                    potential_name = ' '.join(words[start_idx:end_idx])

                    clean_name = re.sub(r'\d+|повтор\w*|раз\w*|кг|з\s*вагою', '', potential_name).strip()
                    clean_name = re.sub(r'\s+', ' ', clean_name)

                    if len(clean_name) > len(exercise):
                        return clean_name
                    else:
                        return exercise

    return None


def format_exercise_summary(exercises_raw):
    """
    Приймає список вправ з БД та форматує їх з групуванням за вагою
    exercises_raw: список кортежів (name, reps, weight) з БД
    """
    exercise_groups = {}

    for name, reps, weight in exercises_raw:
        if name not in exercise_groups:
            exercise_groups[name] = []

        exercise_groups[name].append({
            'reps': reps,
            'weight': weight
        })

    formatted_lines = []

    for exercise_name, entries in exercise_groups.items():
        if len(entries) == 1:
            entry = entries[0]
            line = f"• {exercise_name} – {entry['reps']} повторів"
            if entry['weight']:
                line += f" з вагою {entry['weight']:.0f} кг"
        else:
            weight_groups = {}
            total_reps = 0

            for entry in entries:
                weight_key = entry['weight'] if entry['weight'] else 0
                if weight_key not in weight_groups:
                    weight_groups[weight_key] = 0
                weight_groups[weight_key] += entry['reps']
                total_reps += entry['reps']

            approaches_count = len(entries)
            line = f"• {exercise_name} – {approaches_count} підходи, {total_reps} повторів:\n"

            for weight, reps in sorted(weight_groups.items(), key=lambda x: x[0] or 0, reverse=True):
                if weight > 0:
                    line += f"  - {reps} повторів з вагою {weight:.0f} кг\n"
                else:
                    line += f"  - {reps} повторів без ваги\n"

            line = line.rstrip('\n')

        formatted_lines.append(line)

    return formatted_lines