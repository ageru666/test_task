import asyncio
import signal
import sys
from config import bot
from handlers import dp

async def main():
    """Основна функція запуску бота"""
    try:
        print("Запуск бота...")
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        print(f"Помилка при запуску бота: {e}")
    finally:
        await bot.session.close()


def signal_handler(sig, frame):
    """Обробник сигналу для коректного завершення"""
    print("\nЗупинка бота...")
    sys.exit(0)


if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nБот зупинено користувачем")
    except Exception as e:
        print(f"Критична помилка: {e}")
    finally:
        print("Програма завершена")