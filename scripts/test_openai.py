#!/usr/bin/env python3
# scripts/test_openai.py

"""
Простой тест OpenAI подключения
"""

import asyncio
import os
from dotenv import load_dotenv

# Загружаем .env
load_dotenv()


async def test_openai():
    """Тест OpenAI API"""

    api_key = os.getenv("OPENAI__API_KEY")

    if not api_key or api_key == "sk-your-openai-api-key":
        print("❌ OpenAI API ключ не настроен в .env")
        return False

    print(f"🔑 API ключ: {api_key[:20]}...")

    try:
        from openai import AsyncOpenAI

        print("📦 Создание клиента...")
        client = AsyncOpenAI(api_key=api_key)

        print("🤖 Тестовый запрос...")
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Hello, say 'test successful'"}],
            max_tokens=10
        )

        if response.choices:
            result = response.choices[0].message.content
            print(f"✅ Ответ: {result}")
            print("✅ OpenAI API работает!")
            return True
        else:
            print("❌ Пустой ответ от OpenAI")
            return False

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False


if __name__ == "__main__":
    print("🧪 Тест OpenAI API")
    print("=" * 30)

    success = asyncio.run(test_openai())
    exit(0 if success else 1)