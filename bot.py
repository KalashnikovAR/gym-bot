import logging
import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
from openai import OpenAI

# Получаем ключи из переменных окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

# Этапы диалога
GOAL, STATS = range(2)

logging.basicConfig(level=logging.INFO)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я твой тренер-бот. Напиши, какая у тебя цель: набор массы, сушка или сила?"
    )
    return GOAL

# Получаем цель
async def get_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['goal'] = update.message.text
    await update.message.reply_text("Теперь напиши свой рост и вес через пробел, например: 185 75")
    return STATS

# Получаем рост и вес, отправляем запрос в OpenAI
async def get_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        height, weight = map(int, update.message.text.split())
        goal = context.user_data['goal']

        prompt = (
            f"Пользователь с ростом {height} см и весом {weight} кг хочет {goal}. "
            f"Составь ему эффективный план тренировки в тренажёрном зале на 45 минут, "
            f"с акцентом на его цель."
        )

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.7,
        )

        answer = response.choices[0].message.content
        await update.message.reply_text(answer)
    except Exception as e:
        await update.message.reply_text("Произошла ошибка. Проверь формат данных и попробуй снова.")
        print(e)
    return ConversationHandler.END

# Отмена диалога
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Окей, отмена. Если хочешь начать заново — напиши /start.")
    return ConversationHandler.END

# Запуск бота
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            GOAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_goal)],
            STATS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_stats)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()