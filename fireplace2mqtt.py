import signal
import sys
import paho.mqtt.client as mqtt
import requests
import json
import time
from threading import Thread

# Настройки MQTT

# Читаем конфиг из файла
with open("/mnt/data/python/fireplace_config.json", "r") as config_file:
    config = json.load(config_file)

# Настройки MQTT
BROKER = config["mqtt"]["broker"]
PORT = config["mqtt"]["port"]
USERNAME = config["mqtt"]["username"]
PASSWORD = config["mqtt"]["password"]

# Настройки устройства
DEVICE = config["device"]["name"]
base_url_from_config = config["device"]["base_url"]
BASE_URL = f"http://{base_url_from_config}"
TOPICS = {
    "power_on": f"/devices/{DEVICE}/controls/power_on/on",
    "power_off": f"/devices/{DEVICE}/controls/power_off/on",
    "meta_fireplace": f"/devices/{DEVICE}/meta",
    "meta_power_on": f"/devices/{DEVICE}/controls/power_on/meta",
    "meta_power_off": f"/devices/{DEVICE}/controls/power_off/meta",
    "status": f"/devices/{DEVICE}/controls/status",
    "meta_status": f"/devices/{DEVICE}/controls/status/meta",
    "fire_mode": f"/devices/{DEVICE}/controls/fire_mode/on",
    "meta_fire_mode": f"/devices/{DEVICE}/controls/fire_mode/meta",
    "audio_mode": f"/devices/{DEVICE}/controls/audio_mode/on",
    "meta_audio_mode": f"/devices/{DEVICE}/controls/audio_mode/meta",
    "settings": f"/devices/{DEVICE}/controls/settings/on",
    "meta_settings": f"/devices/{DEVICE}/controls/settings/meta",
    "power_status": f"/devices/{DEVICE}/controls/power_status",
    "meta_power_status": f"/devices/{DEVICE}/controls/power_status/meta",
    "fill_status": f"/devices/{DEVICE}/controls/fill_status",
    "meta_fill_status": f"/devices/{DEVICE}/controls/fill_status/meta",
    "log": f"/devices/{DEVICE}/controls/log",
    "meta_log": f"/devices/{DEVICE}/controls/log/meta" 
}

# Настройки HTTP запросов
HTTP_URLS = {
    "power_on": f"{BASE_URL}/analog?POWER=1",
    "power_off": f"{BASE_URL}/analog?POWER=0",
    "fire_mode_1": f"{BASE_URL}/SAVE?select_rez=1",
    "fire_mode_2": f"{BASE_URL}/SAVE?select_rez=2",
    "fire_mode_3": f"{BASE_URL}/SAVE?select_rez=3",
    "fire_mode_4": f"{BASE_URL}/SAVE?select_rez=4",
    "audio_mode_1": f"{BASE_URL}/SAVE?AUDIO_rej=0",
    "audio_mode_2": f"{BASE_URL}/SAVE?AUDIO_rej=1",
    "audio_mode_3": f"{BASE_URL}/SAVE?AUDIO_rej=2",
    "settings": f"{BASE_URL}/jsonSetings"
}
HEADERS = {"Content-Type": "application/json"}

def send_request(url):
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            print(f"Запрос успешный: {url}")
        else:
            print(f"Ошибка запроса: {response.status_code} для {url}")
    except Exception as e:
        print(f"Ошибка: {e}")

# Функция для получения JSON-данных из HTTP-запроса
def fetch_json(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=5)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Ошибка при получении JSON: {response.status_code} для {url}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Ошибка HTTP-запроса: {e}")
        return None

# Проверка статуса устройства каждые 5 секунд
def check_device_status(client, url, status_topic, power_status_topic, fill_status_topic, log_topic):
    while True:
        try:
            json_data = fetch_json(url)
            if json_data is not None:
                client.publish(status_topic, "online", retain=True)
                client.publish(log_topic, json.dumps(json_data), retain=True)
                power_value = json_data.get("POWER")
                if power_value is not None:
                    client.publish(power_status_topic, 1 if power_value == 1 else 0, retain=True)
                else:
                    print("Ключ 'POWER' не найден в ответе")
                fill_value = json_data.get("zapravka")
                if fill_value is not None:
                    client.publish(fill_status_topic, 1 if fill_value == 1 else 0, retain=True)
                else:
                    print("Ключ 'zapravka' не найден в ответе")
            else:
                client.publish(status_topic, "offline", retain=True)
        except Exception as e:
            print(f"Ошибка при проверке статуса: {e}")
            client.publish(status_topic, "offline", retain=True)
        time.sleep(5)

# Функция обработки сообщений MQTT
def on_message(client, userdata, message):
    if message.topic == TOPICS["power_on"]:
        send_request(HTTP_URLS["power_on"])
    elif message.topic == TOPICS["power_off"]:
        send_request(HTTP_URLS["power_off"])
    elif message.topic == TOPICS["fire_mode"]:
        try:
            mode = int(message.payload.decode())
            if 1 <= mode <= 4:
                url = f"{BASE_URL}/SAVE?select_rez={mode}"
                send_request(url)
            else:
                print(f"Неверный режим: {mode}")
        except ValueError:
            print("Неверное значение для режима огня")
    elif message.topic == TOPICS["audio_mode"]:
        try:
            mode = int(message.payload.decode())
            if 0 <= mode <= 2:
                url = f"{BASE_URL}/SAVE?AUDIO_rej={mode}"
                send_request(url)
            else:
                print(f"Неверный режим звука: {mode}")
        except ValueError:
            print("Неверное значение для режима звука")
    elif message.topic == TOPICS["settings"]:
        json_data = fetch_json(HTTP_URLS["settings"])
        if json_data is not None:
            # Логгирование в консоль
            print(f"Получены настройки: {json.dumps(json_data, indent=2)}")
            # Публикация в топик log
            client.publish(TOPICS["log"], json.dumps(json_data), retain=False)
        else:
            print("Ошибка: Не удалось получить настройки")
    else:
        print(f"Получено сообщение: {message.payload.decode()} на топике {message.topic}")

# Обработчик успешного подключения
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Успешное подключение к MQTT брокеру")

        # Инициализация топиков
        initial_states = {
            TOPICS["power_on"]: "0",
            TOPICS["power_off"]: "0",
            TOPICS["status"]: "offline",
            TOPICS["fire_mode"]: "2",
            TOPICS["audio_mode"]: "1",
            TOPICS["settings"]: "0",
            TOPICS["power_status"]: 0,
            TOPICS["fill_status"]: 0,
            TOPICS["log"]: ""
        }
        
        for topic, state in initial_states.items():
            client.publish(topic, state, retain=True)

        # Метаинформация для всех топиков
        meta_data = {
            TOPICS["meta_fireplace"]: {
                "driver": "wb-rules",
                "title": {"en": "Fireplace", "ru": "Камин"}
            },
            TOPICS["meta_power_on"]: {
                "order": 1,
                "title": {"en": "Power ON", "ru": "Включение"},
                "type": "pushbutton"
            },
            TOPICS["meta_power_off"]: {
                "order": 2,
                "title": {"en": "Power OFF", "ru": "Отключение"},
                "type": "pushbutton"
            },
            TOPICS["meta_fire_mode"]: {
                "order": 3,
                "title": {"en": "Fire Mode", "ru": "Режим огня"},
                "type": "range",
                "min": 1,
                "max": 4
            },
            TOPICS["meta_audio_mode"]: {
                "order": 4,
                "title": {"en": "Audio Mode", "ru": "Режим звука"},
                "type": "range",
                "min": 0,
                "max": 2
            },
            TOPICS["meta_settings"]: {
                "order": 5,
                "title": {"en": "Settings", "ru": "Настройки"},
                "type": "pushbutton"
            },
            TOPICS["meta_status"]: {
                "order": 6,
                "title": {"en": "Status", "ru": "Состояние"},
                "type": "text"
            },
            TOPICS["meta_power_status"]: {
                "order": 7,
                "title": {"en": "Power Status", "ru": "Статус питания"},
                "type": "switch",
                "readonly": True
            },
            TOPICS["meta_fill_status"]: {
                "order": 8,
                "title": {"en": "Fill", "ru": "Заправка"},
                "type": "switch",
                "readonly": True
            },
            TOPICS["meta_log"]: { 
                "order": 9,
                "title": {"en": "Log", "ru": "Лог"},
                "type": "text",
                "readonly": True
            }
        }

        for topic, data in meta_data.items():
            client.publish(topic, json.dumps(data), retain=True)

        client.subscribe([
			(TOPICS["power_on"], 0),	
			(TOPICS["power_off"], 0),	
            (TOPICS["settings"], 0),			
            (TOPICS["status"], 0),
            (TOPICS["fire_mode"], 0),
            (TOPICS["audio_mode"], 0),
            (TOPICS["log"], 0)
        ])

        # Запуск фонового потока для проверки статуса
        Thread(
            target=check_device_status,
            args=(client, HTTP_URLS["settings"], TOPICS["status"], TOPICS["power_status"], TOPICS["fill_status"], TOPICS["log"]),
            daemon=True
        ).start()
    else:
        print(f"Ошибка подключения: {rc}")

# Настройка MQTT-клиента
client = mqtt.Client()
client.on_message = on_message
client.on_connect = on_connect
client.username_pw_set(USERNAME, PASSWORD)
client.connect(BROKER, PORT)

# Функция завершения
def signal_handler(sig, frame):
    print('Остановка программы...')
    client.disconnect()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
client.loop_forever()