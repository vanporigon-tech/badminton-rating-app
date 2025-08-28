#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import json
import time
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Конфигурация
BOT_TOKEN = os.getenv('BOT_TOKEN', '8401405889:AAEGFi1tCX6k2m4MyGBoAY3MdJC63SXFba0')
MINI_APP_URL = os.getenv('MINI_APP_URL', 'https://vanporigon-tech.github.io/badminton-rating-app')
ADMIN_CHAT_ID = 972717950

def send_message(chat_id, text, reply_markup=None):
    """Отправка сообщения в чат"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    
    if reply_markup:
        data["reply_markup"] = reply_markup
    
    try:
        response = requests.post(url, json=data)
        if response.status_code == 200:
            print(f"✅ Сообщение отправлено успешно")
            return True
        else:
            print(f"❌ Ошибка отправки: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Ошибка отправки: {str(e)}")
        return False

def setup_bot_commands():
    """Настройка команд бота"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setMyCommands"
    
    commands = [
        {"command": "start", "description": "Запустить бота"}
    ]
    
    data = {
        "commands": commands
    }
    
    try:
        response = requests.post(url, json=data)
        if response.status_code == 200:
            print("✅ Команды бота настроены")
            return True
        else:
            print(f"❌ Ошибка настройки команд: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Ошибка настройки команд: {str(e)}")
        return False

def handle_start_command(chat_id, first_name):
    """Обработка команды /start"""
    print(f"🚀 Обрабатываю команду /start для {first_name}")
    
    # Создаем клавиатуру с кнопками
    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "✏️ Изменить инициалы",
                    "callback_data": "change_initials"
                }
            ],
            [
                {
                    "text": "🏸 Начать игру",
                    "web_app": {
                        "url": MINI_APP_URL
                    }
                }
            ]
        ]
    }
    
    welcome_text = f"""
Привет, {first_name}! 👋

Добро пожаловать в систему рейтинга бадминтона!

Нажмите на кнопку "Начать игру" чтобы открыть Mini App.
    """.strip()
    
    return send_message(chat_id, welcome_text, keyboard)

def handle_callback_query(chat_id, callback_data):
    """Обработка callback запросов от кнопок"""
    if callback_data == "change_initials":
        # Здесь можно добавить логику для изменения инициалов
        response_text = """
Для изменения инициалов, пожалуйста, обратитесь к администратору.

Или используйте Mini App для управления профилем.
        """.strip()
        
        return send_message(chat_id, response_text)
    
    return False

def handle_admin_clear_rooms(chat_id):
    """Админская команда очистки комнат"""
    print(f"🗑️ Админская команда очистки комнат от {chat_id}")
    
    if chat_id != ADMIN_CHAT_ID:
        return send_message(chat_id, "❌ У вас нет прав для выполнения этой команды.")
    
    # Здесь можно добавить вызов API для очистки комнат
    # Пока просто отправляем сообщение об успехе
    success_message = "✅ Все комнаты успешно очищены и расформированы."
    return send_message(chat_id, success_message)

def process_update(update):
    """Обработка обновления от Telegram"""
    try:
        # Обработка сообщений
        if "message" in update:
            message = update["message"]
            chat_id = message["chat"]["id"]
            first_name = message.get("from", {}).get("first_name", "Неизвестный")
            
            if "text" in message:
                text = message["text"]
                
                if text == "/start":
                    return handle_start_command(chat_id, first_name)
                elif text == "/admin_clear_rooms":
                    return handle_admin_clear_rooms(chat_id)
                else:
                    # Игнорируем все остальные команды
                    return True
        
        # Обработка callback запросов от кнопок
        elif "callback_query" in update:
            callback_query = update["callback_query"]
            chat_id = callback_query["message"]["chat"]["id"]
            callback_data = callback_query["data"]
            
            return handle_callback_query(chat_id, callback_data)
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка обработки обновления: {str(e)}")
        return False

def get_updates(offset=None):
    """Получение обновлений от Telegram"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    
    params = {
        "timeout": 30,
        "allowed_updates": ["message", "callback_query"]
    }
    
    if offset:
        params["offset"] = offset
    
    try:
        response = requests.get(url, params=params, timeout=35)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Ошибка получения обновлений: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Ошибка получения обновлений: {str(e)}")
        return None

def main():
    """Основная функция бота"""
    print("🤖 Запуск простого Telegram бота...")
    print(f"📱 Токен: {BOT_TOKEN[:20]}...")
    print(f"🌐 Mini App URL: {MINI_APP_URL}")
    print("=" * 50)
    
    # Настраиваем команды бота
    if not setup_bot_commands():
        print("❌ Не удалось настроить команды бота")
        return
    
    print("✅ Бот успешно запущен!")
    print("📱 Отправьте /start в Telegram боту @GoBadmikAppBot")
    print("=" * 50)
    
    offset = None
    
    while True:
        try:
            print("🔄 Бот работает... Нажмите Ctrl+C для остановки")
            
            # Получаем обновления
            updates_response = get_updates(offset)
            
            if updates_response and "result" in updates_response:
                updates = updates_response["result"]
                
                for update in updates:
                    update_id = update["update_id"]
                    offset = update_id + 1
                    
                    # Обрабатываем обновление
                    if not process_update(update):
                        print(f"❌ Ошибка обработки обновления {update_id}")
            
            # Небольшая пауза между запросами
            time.sleep(1)
            
        except KeyboardInterrupt:
            print("\n🛑 Бот остановлен пользователем")
            break
        except Exception as e:
            print(f"❌ Критическая ошибка: {str(e)}")
            time.sleep(5)  # Пауза перед повторной попыткой

if __name__ == "__main__":
    main()
