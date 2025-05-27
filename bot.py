import logging
import os
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    filters,
)
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Конфигурация
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
FOLDER_ID = os.getenv("FOLDER_ID")

# Проверка обязательных переменных
if not all([TELEGRAM_TOKEN, YANDEX_API_KEY, FOLDER_ID]):
    raise ValueError("Не все обязательные переменные окружения заданы!")

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния диалога
CHOOSE_GOAL, CHOOSE_LEVEL, CHOOSE_TYPE, ENTER_STATS = range(4)

# Хранилище данных пользователей
user_data_store = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    keyboard = [
        [InlineKeyboardButton("🏋️ Набор массы", callback_data="goal_mass")],
        [InlineKeyboardButton("🔥 Сушка", callback_data="goal_cut")],
        [InlineKeyboardButton("💪 Сила", callback_data="goal_strength")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(
            "Выбери свою цель:",
            reply_markup=reply_markup
        )
    else:
        await update.callback_query.edit_message_text(
            "Выбери свою цель:",
            reply_markup=reply_markup
        )

    return CHOOSE_GOAL


async def button_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора цели."""
    query = update.callback_query
    await query.answer()

    goal_map = {
        "goal_mass": "набор массы",
        "goal_cut": "сушка",
        "goal_strength": "сила"
    }

    context.user_data["goal"] = goal_map[query.data]

    keyboard = [
        [InlineKeyboardButton("👶 Новичок", callback_data="level_beginner")],
        [InlineKeyboardButton("👨 Средний", callback_data="level_intermediate")],
        [InlineKeyboardButton("👴 Продвинутый", callback_data="level_advanced")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "Выбери уровень подготовки:",
        reply_markup=reply_markup
    )

    return CHOOSE_LEVEL


async def button_level(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора уровня подготовки."""
    query = update.callback_query
    await query.answer()

    level_map = {
        "level_beginner": "новичок",
        "level_intermediate": "средний",
        "level_advanced": "продвинутый"
    }

    context.user_data["level"] = level_map[query.data]

    keyboard = [
        [InlineKeyboardButton("🔄 Фулбади", callback_data="type_fullbody")],
        [InlineKeyboardButton("📊 Сплит", callback_data="type_split")],
        [InlineKeyboardButton("🏃‍ Кардио + Силовая", callback_data="type_cardio")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "Выбери тип тренировки:",
        reply_markup=reply_markup
    )

    return CHOOSE_TYPE


async def button_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора типа тренировки."""
    query = update.callback_query
    await query.answer()

    type_map = {
        "type_fullbody": "фулбади",
        "type_split": "сплит",
        "type_cardio": "кардио + силовая"
    }

    context.user_data["type"] = type_map[query.data]

    await query.edit_message_text(
        "Теперь введи свой рост (в см) и вес (в кг) через пробел (например: 185 75):"
    )

    return ENTER_STATS


async def enter_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ввода роста и веса."""
    user_id = update.effective_user.id

    try:
        height, weight = map(int, update.message.text.strip().split())

        if height < 100 or height > 250 or weight < 30 or weight > 200:
            raise ValueError("Некорректные параметры")

        user_data = {
            "goal": context.user_data["goal"],
            "level": context.user_data.get("level", "средний"),
            "type": context.user_data.get("type", "фулбади"),
            "height": height,
            "weight": weight,
            "history": []
        }

        user_data_store[user_id] = user_data

        response = await generate_workout(
            goal=user_data["goal"],
            height=height,
            weight=weight,
            level=user_data["level"],
            workout_type=user_data["type"]
        )

        user_data["history"].append(response)

        # Кнопки после генерации
        keyboard = [
            [
                InlineKeyboardButton("🔄 Сгенерировать ещё", callback_data="regenerate"),
                InlineKeyboardButton("📋 История", callback_data="show_history"),
            ],
            [InlineKeyboardButton("✏️ Новый запрос", callback_data="new_request")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(response, reply_markup=reply_markup)

    except ValueError as e:
        await update.message.reply_text(
            "Неверный формат. Пожалуйста, введи два числа через пробел (например: 185 75). "
            "Рост должен быть от 100 до 250 см, вес от 30 до 200 кг."
        )
        return ENTER_STATS
    except Exception as e:
        logger.error(f"Error in enter_stats: {e}")
        await update.message.reply_text(
            "Произошла ошибка. Попробуй ещё раз или начни заново /start"
        )

    return ConversationHandler.END


async def generate_workout(goal: str, height: int, weight: int, level: str, workout_type: str) -> str:
    """Генерация плана тренировки с помощью YandexGPT."""
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json"
    }

    prompt = (
        f"Создай подробную программу тренировки для человека с параметрами:\n"
        f"- Рост: {height} см\n"
        f"- Вес: {weight} кг\n"
        f"- Цель: {goal}\n"
        f"- Уровень подготовки: {level}\n"
        f"- Тип тренировки: {workout_type}\n\n"
        "Программа должна быть на 45-60 минут, с разбивкой по упражнениям, "
        "подходам и повторениям. Укажи рекомендации по весам и отдыху между подходами. "
        "Дай краткие пояснения по технике выполнения."
    )

    data = {
        "modelUri": f"gpt://{FOLDER_ID}/yandexgpt-lite/latest",
        "completionOptions": {
            "stream": False,
            "temperature": 0.6,
            "maxTokens": 2000
        },
        "messages": [{"role": "user", "text": prompt}]
    }

    try:
        logger.info(f"Sending request to YandexGPT: {data}")

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                response_text = await response.text()

                if response.status != 200:
                    logger.error(f"YandexGPT API error: {response_text}")
                    return f"⚠️ Ошибка API (код {response.status}): {response_text}"

                result = await response.json()
                logger.info(f"Received response from YandexGPT: {result}")

                if "result" not in result or "alternatives" not in result["result"]:
                    return "⚠️ Неожиданный формат ответа от API"

                return result["result"]["alternatives"][0]["message"]["text"]

    except Exception as e:
        logger.error(f"Error in generate_workout: {e}")
        return f"⚠️ Произошла ошибка при генерации: {str(e)}"


async def regenerate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик повторной генерации тренировки."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    if user_id not in user_data_store:
        await query.edit_message_text(
            "Данные устарели. Начни заново: /start"
        )
        return

    user_data = user_data_store[user_id]

    try:
        # Показываем уведомление о начале генерации
        await query.edit_message_text("🔄 Генерирую новый вариант...")

        response = await generate_workout(
            goal=user_data["goal"],
            height=user_data["height"],
            weight=user_data["weight"],
            level=user_data["level"],
            workout_type=user_data["type"]
        )

        user_data["history"].append(response)

        keyboard = [
            [
                InlineKeyboardButton("🔄 Сгенерировать ещё", callback_data="regenerate"),
                InlineKeyboardButton("📋 История", callback_data="show_history"),
            ],
            [InlineKeyboardButton("✏️ Новый запрос", callback_data="new_request")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(response, reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Error in regenerate: {e}")
        await query.edit_message_text(
            "⚠️ Произошла ошибка при генерации. Попробуй ещё раз."
        )


async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик показа истории тренировок."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    if user_id not in user_data_store or not user_data_store[user_id]["history"]:
        await query.answer("История пуста!", show_alert=True)
        return

    history = user_data_store[user_id]["history"]
    message = "📚 Последние тренировки:\n\n" + "\n\n---\n\n".join(
        f"🏋️ Тренировка #{i + 1}:\n{workout[:1000]}..." for i, workout in enumerate(history[-3:])
    )

    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_last")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(message, reply_markup=reply_markup)


async def back_to_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат к последней тренировке."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    if user_id not in user_data_store or not user_data_store[user_id]["history"]:
        await query.answer("Нет последней тренировки!", show_alert=True)
        return

    last_workout = user_data_store[user_id]["history"][-1]

    keyboard = [
        [
            InlineKeyboardButton("🔄 Сгенерировать ещё", callback_data="regenerate"),
            InlineKeyboardButton("📋 История", callback_data="show_history"),
        ],
        [InlineKeyboardButton("✏️ Новый запрос", callback_data="new_request")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(last_workout, reply_markup=reply_markup)


async def new_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нового запроса."""
    query = update.callback_query
    await query.answer()

    # Очищаем текущие данные
    if update.effective_user.id in user_data_store:
        del user_data_store[update.effective_user.id]

    # Начинаем заново
    await start(update, context)
    return CHOOSE_GOAL


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик отмены."""
    await update.message.reply_text("Диалог прерван. Начни заново: /start")
    return ConversationHandler.END


def main():
    """Запуск бота."""
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSE_GOAL: [CallbackQueryHandler(button_goal)],
            CHOOSE_LEVEL: [CallbackQueryHandler(button_level)],
            CHOOSE_TYPE: [CallbackQueryHandler(button_type)],
            ENTER_STATS: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_stats)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Регистрация обработчиков
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(regenerate, pattern="^regenerate$"))
    application.add_handler(CallbackQueryHandler(show_history, pattern="^show_history$"))
    application.add_handler(CallbackQueryHandler(back_to_last, pattern="^back_to_last$"))
    application.add_handler(CallbackQueryHandler(new_request, pattern="^new_request$"))

    # Запуск бота
    logger.info("Бот запущен...")
    application.run_polling()


if __name__ == "__main__":
    main()