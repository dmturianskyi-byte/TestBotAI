import ollama

from tools import search_pharmacies
from prompts import SYSTEM_PROMPT


client = ollama.Client(host="http://ollama:11434")


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_pharmacies",
            "description": (
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
            "parameters": {
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
                        "description": "Максимум результатів у списку, за замовчуванням 20."
                    }
                },
                "required": []
            }
        }
    }
]


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
            limit=args.get("limit", 20),
        )
        return result

    print(f"[TOOL] ⚠️ Невідомий tool: {name}")
    return []


def ask_ai(user_text: str) -> str:

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_text}
    ]

    print(f"\n{'='*50}")
    print(f"[AI] Запит: {user_text}")

    response = client.chat(
        model="qwen3:8b",
        messages=messages,
        tools=TOOLS
    )

    msg = response["message"]

    if "tool_calls" not in msg or not msg["tool_calls"]:
        print("[AI] ⚠️ Жоден tool не викликано!")
        return msg.get("content", "Не вдалося обробити запит.")

    tool_results = []

    for tool in msg["tool_calls"]:
        name = tool["function"]["name"]
        args = tool["function"]["arguments"]
        result = call_tool(name, args)
        tool_results.append(str(result))

    messages.append(msg)
    messages.append({
        "role": "tool",
        "content": "\n".join(tool_results)
    })

    print(f"[AI] Генерую відповідь на основі {len(tool_results)} результатів...")

    final = client.chat(
        model="qwen3:8b",
        messages=messages
    )

    answer = final["message"]["content"]
    print(f"[AI] ✅ Відповідь готова ({len(answer)} символів)")

    return answer