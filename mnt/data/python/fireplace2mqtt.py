import json
import time
import requests
import paho.mqtt.client as mqtt
import logging
import signal
import sys
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S"  # Формат времени: часы:минуты:секунды
)
logger = logging.getLogger(__name__)

# Загрузка конфигурации из файла
CONFIG_FILE = "/mnt/data/python/fireplace_config.json"

def load_config():
    """Загружает конфигурацию из JSON-файла."""
    try:
        with open(CONFIG_FILE, "r") as file:
            config = json.load(file)
            # Убедимся, что debug является булевым значением
            if "device" in config and "debug" in config["device"]:
                if isinstance(config["device"]["debug"], str):
                    # Если debug задан как строка, преобразуем в булевый тип
                    config["device"]["debug"] = config["device"]["debug"].lower() == "true"
                # Если debug уже булевый, оставляем как есть
            return config
    except Exception as e:
        logger.error(f"Ошибка загрузки конфигурации: {e}")
        raise

# Загрузка конфигурации
config = load_config()

# Параметры MQTT
MQTT_BROKER = config["mqtt"]["broker"]
MQTT_PORT = config["mqtt"]["port"]
MQTT_USERNAME = config["mqtt"]["username"]
MQTT_PASSWORD = config["mqtt"]["password"]
MQTT_CLIENT_NAME = config["mqtt"]["name"]

# Параметры устройства
DEVICE_BASE_URL = f"http://{config['device']['base_url']}"
DEVICE = "fireplace"  # Имя устройства
DEBUG_MODE = config["device"].get("debug", False)  # Режим отладки

# Топики MQTT
LOG_TOPIC = f"/devices/{DEVICE}/controls/log"
LOG_META_TOPIC = f"/devices/{DEVICE}/controls/log/meta"
DEVICE_META_TOPIC = f"/devices/{DEVICE}/meta"
POWER_TOPIC = f"/devices/{DEVICE}/controls/power"
POWER_META_TOPIC = f"/devices/{DEVICE}/controls/power/meta"
POWER_META_TYPE_TOPIC = f"/devices/{DEVICE}/controls/power/meta/type"
POWER_ON_TOPIC = f"/devices/{DEVICE}/controls/power/on"
POWER_ERROR_TOPIC = f"/devices/{DEVICE}/controls/power/error"
FIRE_MODE_TOPIC = f"/devices/{DEVICE}/controls/fire_mode"
FIRE_MODE_ON_TOPIC = f"/devices/{DEVICE}/controls/fire_mode/on"
FIRE_MODE_META_TOPIC = f"/devices/{DEVICE}/controls/fire_mode/meta"
FIRE_MODE_ERROR_TOPIC = f"/devices/{DEVICE}/controls/fire_mode/error"
AUDIO_MODE_TOPIC = f"/devices/{DEVICE}/controls/audio_mode"
AUDIO_MODE_ON_TOPIC = f"/devices/{DEVICE}/controls/audio_mode/on"
AUDIO_MODE_META_TOPIC = f"/devices/{DEVICE}/controls/audio_mode/meta"
AUDIO_MODE_ERROR_TOPIC = f"/devices/{DEVICE}/controls/audio_mode/error"

# Создание MQTT-клиента
mqtt_client = mqtt.Client(MQTT_CLIENT_NAME)
mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

# Флаг для корректного завершения программы
running = True

def signal_handler(sig, frame):
    """Обработчик сигналов для корректного завершения программы."""
    global running
    logger.info("Получен сигнал завершения. Завершение работы...")
    running = False
    sys.exit(0)

# Регистрация обработчика сигналов
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def on_connect(client, userdata, flags, rc):
    """Обработчик подключения к MQTT-брокеру."""
    if rc == 0:
        logger.info("Успешное подключение к MQTT-брокеру")
        # Публикация meta-топиков
        publish_meta_topics()
        # Подписка на топики управления
        mqtt_client.subscribe(POWER_ON_TOPIC)
        mqtt_client.subscribe(FIRE_MODE_ON_TOPIC)
        mqtt_client.subscribe(AUDIO_MODE_ON_TOPIC)
    else:
        logger.error(f"Ошибка подключения к MQTT-брокеру: {rc}")

def on_disconnect(client, userdata, rc):
    """Обработчик отключения от MQTT-брокера."""
    if rc != 0:
        logger.warning("Отключение от MQTT-брокера. Попытка переподключения...")
        while running:
            try:
                mqtt_client.reconnect()
                logger.info("Переподключение к MQTT-брокеру успешно")
                break
            except Exception as e:
                logger.error(f"Ошибка переподключения: {e}. Повторная попытка через 5 секунд...")
                time.sleep(5)

def publish_meta_topics():
    """Публикует meta-топики для корректного отображения в интерфейсе."""
    # Meta для лога
    log_meta = {
        "order": 4,
        "title": {"en": "Log", "ru": "Лог"},
        "type": "text",
        "readonly": True
    }
    mqtt_client.publish(LOG_META_TOPIC, json.dumps(log_meta), retain=True)

    # Meta для управления power
    power_meta = {
        "order": 1,
        "title": {"en": "Power", "ru": "Включение"},
        "type": "switch",
        "readonly": False
    }
    mqtt_client.publish(POWER_META_TOPIC, json.dumps(power_meta), retain=True)

    # Type для power (используется в SprutHub для поиска)
    power_meta_type = "switch"
    mqtt_client.publish(POWER_META_TYPE_TOPIC, power_meta_type, retain=True)

    # Meta для fire_mode
    fire_mode_meta = {
        "order": 2,
        "title": {"en": "Fire Mode", "ru": "Режим огня"},
        "type": "range",
        "min": 0,
        "max": 3
    }
    mqtt_client.publish(FIRE_MODE_META_TOPIC, json.dumps(fire_mode_meta), retain=True)

    # Meta для audio_mode
    audio_mode_meta = {
        "order": 3,
        "title": {"en": "Audio Mode", "ru": "Режим звука"},
        "type": "range",
        "min": 0,
        "max": 2
    }
    mqtt_client.publish(AUDIO_MODE_META_TOPIC, json.dumps(audio_mode_meta), retain=True)

    # Meta для устройства
    device_meta = {
        "driver": "wb-rules",
        "title": {"en": "Fireplace", "ru": "Камин"}
    }
    mqtt_client.publish(DEVICE_META_TOPIC, json.dumps(device_meta), retain=True)

    logger.info("Meta-топики опубликованы")

def fetch_device_data():
    """Запрашивает данные у камина."""
    try:
        response = requests.get(f"{DEVICE_BASE_URL}/jsonSetings", timeout=5)  # Таймаут 5 секунд
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка запроса данных у камина: {e}")
        return None

def send_command(url):
    """Отправляет команду на устройство."""
    try:
        response = requests.post(url, timeout=5)  # Таймаут 5 секунд
        response.raise_for_status()
        logger.info(f"Команда отправлена: {url}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка отправки команды: {e}")

def on_message(client, userdata, msg):
    """Обработчик входящих MQTT-сообщений."""
    if DEBUG_MODE:
        logger.debug(f"Получено сообщение: {msg.topic} - {msg.payload.decode()}")

    # Обработка команд для power/on
    if msg.topic == POWER_ON_TOPIC:
        try:
            payload = msg.payload.decode().strip().lower()
            if payload in ["1", "0"]:
                power_value = 1 if payload in ["1"] else 0
                send_command(f"{DEVICE_BASE_URL}/analog?POWER={power_value}")
                mqtt_client.publish(POWER_TOPIC, str(power_value), retain=False)
        except Exception as e:
            logger.error(f"Ошибка обработки команды для power/on: {e}")

    # Обработка команд для fire_mode/on
    elif msg.topic == FIRE_MODE_ON_TOPIC:
        try:
            fire_mode = int(msg.payload.decode().strip())
            if 0 <= fire_mode <= 3:
                send_command(f"{DEVICE_BASE_URL}/SAVE?select_rez={fire_mode}")
                mqtt_client.publish(FIRE_MODE_TOPIC, str(fire_mode), retain=False)
            else:
                logger.warning(f"Некорректное значение для fire_mode: {fire_mode}")
        except (ValueError, TypeError) as e:
            logger.error(f"Ошибка обработки команды для fire_mode/on: {e}")

    # Обработка команд для audio_mode/on
    elif msg.topic == AUDIO_MODE_ON_TOPIC:
        try:
            audio_mode = int(msg.payload.decode().strip())
            if 0 <= audio_mode <= 2:
                send_command(f"{DEVICE_BASE_URL}/SAVE?AUDIO_rej={audio_mode}")
                mqtt_client.publish(AUDIO_MODE_TOPIC, str(audio_mode), retain=False)
            else:
                logger.warning(f"Некорректное значение для audio_mode: {audio_mode}")
        except (ValueError, TypeError) as e:
            logger.error(f"Ошибка обработки команды для audio_mode/on: {e}")

def main():
    """Основной цикл программы."""
    global running

    # Настройка уровня логирования
    if DEBUG_MODE:
        logger.setLevel(logging.DEBUG)
        logger.info("Режим отладки включен")
    else:
        logger.setLevel(logging.INFO)
        mqtt_client.publish(LOG_TOPIC, "Debugging OFF", retain=False)  # Записываем "Debugging OFF"
        logger.info("Режим отладки выключен")

    # Настройка обработчиков MQTT
    mqtt_client.on_connect = on_connect
    mqtt_client.on_disconnect = on_disconnect
    mqtt_client.on_message = on_message

    # Подключение к MQTT-брокеру
    while running:
        try:
            mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
            break
        except Exception as e:
            logger.error(f"Ошибка подключения к MQTT-брокеру: {e}. Повторная попытка через 5 секунд...")
            time.sleep(5)

    mqtt_client.loop_start()

    # Флаг для отслеживания состояния ошибки
    error_state = False

    # Основной цикл
    while running:
        # Запрос данных у камина
        data = fetch_device_data()
        if data:
            # Если данные пришли, сбрасываем ошибку
            if error_state:
                mqtt_client.publish(POWER_ERROR_TOPIC, "", retain=False)
                mqtt_client.publish(FIRE_MODE_ERROR_TOPIC, "", retain=False)
                mqtt_client.publish(AUDIO_MODE_ERROR_TOPIC, "", retain=False)
                error_state = False

            if DEBUG_MODE:
                logger.debug(f"Получены данные: {json.dumps(data, indent=2)}")  # Логируем данные в режиме отладки
                # Публикация данных в топик лога
                mqtt_client.publish(LOG_TOPIC, json.dumps(data), retain=False)
            else:
                mqtt_client.publish(LOG_TOPIC, "Debugging OFF", retain=False)

            # Обновление топика power
            if "POWER" in data:
                try:
                    power_value = int(data["POWER"])
                    mqtt_client.publish(POWER_TOPIC, str(power_value), retain=False)
                except (ValueError, TypeError) as e:
                    logger.error(f"Ошибка преобразования POWER: {e}")

            # Обновление топика fire_mode
            if "select_rez" in data:
                try:
                    fire_mode = int(data["select_rez"])
                    mqtt_client.publish(FIRE_MODE_TOPIC, str(fire_mode), retain=False)
                except (ValueError, TypeError) as e:
                    logger.error(f"Ошибка преобразования select_rez: {e}")

            # Обновление топика audio_mode
            if "AUDIO_rej" in data:
                try:
                    audio_mode = int(data["AUDIO_rej"])
                    mqtt_client.publish(AUDIO_MODE_TOPIC, str(audio_mode), retain=False)
                except (ValueError, TypeError) as e:
                    logger.error(f"Ошибка преобразования AUDIO_rej: {e}")
        else:
            # Если данные не пришли, публикуем ошибку
            if not error_state:
                mqtt_client.publish(POWER_ERROR_TOPIC, "r", retain=False)
                mqtt_client.publish(FIRE_MODE_ERROR_TOPIC, "r", retain=False)
                mqtt_client.publish(AUDIO_MODE_ERROR_TOPIC, "r", retain=False)
                error_state = True
                logger.warning("Данные от камина не получены. Ошибка записана в топики.")

        # Ожидание 10 секунд
        time.sleep(10)

    # Корректное завершение работы
    logger.info("Завершение работы программы...")
    mqtt_client.loop_stop()
    mqtt_client.disconnect()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Ошибка в работе программы: {e}")
    finally:
        logger.info("Программа завершена")