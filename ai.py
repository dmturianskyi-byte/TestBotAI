import os
import time

from google import genai
from google.genai import types
from google.genai.errors import ServerError, ClientError

from tools import search_pharmacies
from prompts import SYSTEM_PROMPT


client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# Моделі: легша/швидша для виклику tool, трохи потужніша для фінальної відповіді
MODEL_TOOL_CALL = "gemma-4-31b-it"
MODEL_FINAL_ANSWER = "gemma-4-31b-it"

# Якщо основна модель перевантажена (503) — пробуємо цю
FALLBACK_MODEL = "gemma-4-31b-it"

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2  # буде 2s, 4s, 8s (експоненційно)


def generate_with_retry(model: str, contents, config, fallback_model: str | None = None):
    """Викликає Gemini з retry при 503 (перевантаження) і fallback на іншу модель."""
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except ServerError as e:
            last_error = e
            print(f"[AI] ⚠️ ServerError ({model}), спроба {attempt + 1}/{MAX_RETRIES}: {e}")
            time.sleep(RETRY_DELAY_SECONDS * (2 ** attempt))
        except ClientError as e:
            # 429 (квота), 400 (погані параметри) і т.п. — повторювати немає сенсу
            print(f"[AI] ❌ ClientError ({model}): {e}")
            raise

    if fallback_model and fallback_model != model:
        print(f"[AI] ⚠️ Модель {model} недоступна, пробую fallback {fallback_model}...")
        try:
            return client.models.generate_content(
                model=fallback_model,
                contents=contents,
                config=config,
            )
        except (ServerError, ClientError) as e:
            print(f"[AI] ❌ Fallback {fallback_model} теж не відповів: {e}")
            last_error = e

    raise last_error


search_pharmacies_declaration = types.FunctionDeclaration(
    name="search_pharmacies",
    description=(
        "Універсальний пошук аптек у базі. Передавай тільки ті параметри, "
        "які потрібні для конкретного запиту користувача — решту не вказуй.\n\n"
        "Приклади використання:\n"
        "- 'скільки аптек X' → query=X, count_only=true\n"
        "- 'скільки аптек X у місті Y' → query=X, city=Y, count_only=true\n"
        "- 'покажи аптеки X' → query=X\n"
        "- 'аптеки у місті Y' → city=Y\n"
        "- 'аптеки біля адреси Z' → address=Z, radius=500-1000\n"
        "- 'у якому місті найбільше аптек' → group_by_city=true\n"
        "- 'конкуренти біля аптеки на адресі Z' → address=Z, radius=500\n\n"
        "Пошук по назві (query) працює навіть з частковими/скороченими назвами "
        "та варіаціями написання (наприклад '911' знайде 'Аптека 9-1-1')."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Назва або опис аптеки для семантичного пошуку. Не вказуй, якщо запит не про конкретну назву."
            },
            "city": {
                "type": "string",
                "description": "Назва міста для фільтрації, наприклад 'Київ'. Не вказуй для адрес чи координат."
            },
            "address": {
                "type": "string",
                "description": "Конкретна адреса (вулиця, будинок, місто) для геопошуку, наприклад 'вул. Хрещатик 1, Київ'."
            },
            "radius": {
                "type": "integer",
                "description": "Радіус пошуку в метрах. Використовується тільки разом з address. За замовчуванням 1000."
            },
            "count_only": {
                "type": "boolean",
                "description": "true якщо потрібна тільки кількість (запит типу 'скільки')."
            },
            "group_by_city": {
                "type": "boolean",
                "description": "true для запитів про статистику по містах (де найбільше/найменше аптек)."
            },
            "limit": {
                "type": "integer",
                "description": "Максимум результатів у списку."
            }
        },
        "required": []
    }
)

TOOLS = [types.Tool(function_declarations=[search_pharmacies_declaration])]


def call_tool(name: str, args: dict):
    print(f"\n[TOOL CALL] {name} → {args}")

    if name == "search_pharmacies":
        result = search_pharmacies(
            query=args.get("query"),
            city=args.get("city"),
            address=args.get("address"),
            radius=args.get("radius", 1000),
            count_only=args.get("count_only", False),
            group_by_city=args.get("group_by_city", False),
            limit=args.get("limit", None),
        )
        return result

    print(f"[TOOL] ⚠️ Невідомий tool: {name}")
    return []


def ask_ai(user_text: str) -> str:

    print(f"\n{'='*50}")
    print(f"[AI] Запит: {user_text}")

    try:
        return _ask_ai_inner(user_text)
    except (ServerError, ClientError) as e:
        print(f"[AI] ❌ Gemini недоступний: {e}")
        return "Сервіс зараз перевантажений, спробуйте, будь ласка, ще раз через хвилину."
    except Exception as e:
        print(f"[AI] ❌ Неочікувана помилка: {e}")
        return "Сталася помилка під час обробки запиту, спробуйте перефразувати."


def _ask_ai_inner(user_text: str) -> str:
    contents = [
        types.Content(role="user", parts=[types.Part(text=user_text)])
    ]

    response = generate_with_retry(
        model=MODEL_TOOL_CALL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=TOOLS,
            max_output_tokens=8192,
        ),
        fallback_model=FALLBACK_MODEL,
    )

    candidate = response.candidates[0]
    function_calls = [
        part.function_call
        for part in candidate.content.parts
        if part.function_call is not None
    ]

    if not function_calls:
        print("[AI] ⚠️ Жоден tool не викликано!")
        return extract_text(response) or "Не вдалося обробити запит."

    # Додаємо відповідь моделі (з function_call) в історію
    contents.append(candidate.content)

    tool_response_parts = []
    for fc in function_calls:
        name = fc.name
        args = dict(fc.args)
        result = call_tool(name, args)
        tool_response_parts.append(
            types.Part.from_function_response(
                name=name,
                response={"result": result},
            )
        )

    # Додаємо результати tool-викликів як одне "user"-повідомлення з function_response
    contents.append(types.Content(role="user", parts=tool_response_parts))

    print(f"[AI] Генерую відповідь на основі {len(function_calls)} результатів...")

    final = generate_with_retry(
        model=MODEL_FINAL_ANSWER,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=8192,  # щоб великий аналіз (багато аптек) не обрізався
        ),
        fallback_model=None,
    )

    answer = extract_text(final)

    if not answer:
        print(f"[AI] ⚠️ Модель не повернула текст. finish_reason="
              f"{final.candidates[0].finish_reason if final.candidates else 'NO_CANDIDATES'}")
        return "Не вдалося згенерувати відповідь, спробуйте перефразувати запит."

    print(f"[AI] ✅ Відповідь готова ({len(answer)} символів)")

    return answer


def extract_text(response):

    if not response.candidates:
        return None

    candidate = response.candidates[0]

    if not candidate.content:
        return None

    answer = []

    for part in candidate.content.parts:

        if getattr(part, "thought", False):
            print("[DEBUG] Пропускаю thought part")
            continue

        if getattr(part, "text", None):
            answer.append(part.text)

    return "\n".join(answer) if answer else None