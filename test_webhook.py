import httpx
import json
from datetime import datetime

# Test payload simulating Read AI webhook
test_payload = {
    "meeting_id": "readai-test-456",
    "meeting_title": "Weekly 1:1 - Dmitriy & Manager",
    "start_time": datetime.now().isoformat(),
    "end_time": datetime.now().isoformat(),
    "participants": [
        {"name": "Dmitriy Takmakov", "email": "dmitriy@example.com", "is_host": False},
        {"name": "Manager", "email": "manager@example.com", "is_host": True}
    ],
    "transcript": """
    Manager: Привет, Дима! Спасибо что нашел время. Как у тебя дела?
    Dmitriy: Привет! Всё хорошо, спасибо. Есть несколько вещей, которые хотел обсудить.
    Manager: Отлично, давай начнем. Как продвигается работа над новым API?
    Dmitriy: Хорошо, основной функционал готов. Сейчас работаю над тестами и документацией.
    Думаю к концу недели всё будет готово к ревью.
    Manager: Звучит здорово! По документации - можешь добавить примеры использования для каждого endpoint?
    Dmitriy: Да, конечно. Добавлю примеры для каждого метода с curl и Python.
    Manager: Отлично. Ещё вопрос - как ты себя чувствуешь с нагрузкой? Не перегружен?
    Dmitriy: Нет, всё нормально. Нагрузка адекватная, успеваю всё делать.
    Manager: Хорошо слышать. Я со своей стороны посмотрю на ресурсы команды и подумаю,
    может ли кто-то помочь тебе с тестированием. Также поговорю с HR о твоём повышении,
    мы это уже долго обсуждаем.
    Dmitriy: О, спасибо большое! Буду рад любой помощи.
    Manager: Давай также созвонимся в пятницу после твоего ревью, чтобы обсудить следующие задачи на спринт.
    Dmitriy: Договорились! В пятницу после обеда удобно?
    Manager: Да, идеально. Запланирую встречу. Ещё что-то хочешь обсудить?
    Dmitriy: Нет, вроде всё. Спасибо!
    Manager: Отлично, тогда до пятницы. Удачи с ревью!
    """,
    "summary": "Обсуждение прогресса по API разработке и планирование встречи на пятницу"
}

async def test_webhook():
    print("🧪 Тестирование создания 1:1 и задач из транскрипта...\n")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/webhook/test",
            json=test_payload,
            timeout=60.0
        )

        print(f"✅ Статус: {response.status_code}")
        result = response.json()
        print(f"\n📄 Результат:")
        print(f"  - Репорт: {result['report_name']}")
        print(f"  - Дата встречи: {result['meeting_date']}")
        print(f"  - ID страницы: {result['notion_page_id']}")
        print(f"  - URL: {result['notion_url']}")
        print(f"\n🔗 Проверь страницу 1:1 и базу Tasks в Notion!")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_webhook())
