import logging
import os
import sys
import time
from contextlib import suppress
from http import HTTPStatus

import requests
from dotenv import load_dotenv
from telebot import TeleBot, apihelper

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s - %(funcName)s - [%(levelname)s] - %(lineno)d- %(message)s')
handler = logging.StreamHandler(stream=sys.stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)


def check_tokens() -> None:
    """
    Проверяет доступность переменных окружения.
    Проверка токенов Практикума и
    Bot API, id чата получателя. Возвращает булево значение.
    """
    venv_tokens = ('PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID')
    missng_tokens = [token for token in venv_tokens if not globals()[token]]
    if missng_tokens:
        message = (
            f'Отсутсвуют переменные окружения: {", ".join(missng_tokens)}')
        logger.critical(message)
        raise ValueError(message)


def send_message(bot: TeleBot, message: str) -> None:
    """
    Отправляет сообщение в Telegram-чат.
    Принимает на вход два параметра:
    экземпляр класса TeleBot и строку с текстом сообщения.
    """
    logger.debug(f'Отправляем сообщение: {message}')
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    logger.debug(f'Сообщение отправлено. {message}')


def get_api_answer(timestamp: int) -> dict:
    """
    Делает запрос к единственному эндпоинту API-сервиса.
    В качестве параметра в функцию передаётся временная метка.
    В случае успешного запроса должна вернуть ответ API, приведя его из
    формата JSON к типам данных Python.
    """
    logger.debug(f'Получаем ответ от API за последние {timestamp}')
    try:
        homework_statuses = requests.get(ENDPOINT,
                                         headers=HEADERS,
                                         params={'from_date': timestamp})

    except requests.RequestException as error:
        message = f'Эндпоинт API недоступен: {error}'
        raise ConnectionError(message)

    if homework_statuses.status_code != HTTPStatus.OK:
        raise ValueError(
            f'Ошибка при запросе к API: {homework_statuses.status_code}')

    return homework_statuses.json()


def check_response(response: dict) -> None:
    """
    Проверяет ответ API на соответствие документации.
    В качестве параметра функция получает ответ API,
    приведённый к типам данных Python.
    """
    logger.debug('Проверяем ответ API')
    if not isinstance(response, dict):
        raise TypeError(f'Ответ не содержит словарь {type(response)}')
    homeworks = response.get('homeworks')
    if not homeworks:
        raise KeyError('В ответе отсутсвует ключ "homeworks"')
    if not isinstance(homeworks, list):
        raise TypeError(f'Ответ не содержит словарь {type(response)}')


def parse_status(homework: dict) -> str:
    """
    Извлекает из информации о конкретной домашней работе статус этой работы.
    В качестве параметра функция получает только один элемент
    из списка домашних работ. В случае успеха функция возвращает
    подготовленную для отправки в Telegram строку, содержащую один из
    вердиктов словаря HOMEWORK_VERDICTS
    """
    logger.debug(f'Получаем статус домашней работы: {homework}')
    try:
        homework_name = homework['homework_name']

    except KeyError as error:
        message = f'Ключ {error} отсутсвует в домашней работе'
        raise KeyError(message)

    if not homework.get('status'):
        raise KeyError('Ключ "status" отсутсвует в домашней работе')
    try:
        verdict = HOMEWORK_VERDICTS[homework['status']]

    except KeyError as error:
        message = f'{error}. Неизвестный статус домашней работы'
        raise ValueError(message)

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    check_tokens()

    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())

    last_message = ''

    while True:
        try:
            homework_statuses = get_api_answer(timestamp)
            check_response(homework_statuses)
            homeworks = homework_statuses.get('homeworks')
            if homeworks:
                message = parse_status(homeworks[0])
                if message != last_message:
                    send_message(bot, message)
                    last_message = message
            else:
                logger.info('Отсутсвует обновление статуса домашней работы')

            timestamp = homework_statuses.get('current_date', timestamp)

        except apihelper.ApiTelegramException as telegram_error:
            logger.error(f'Ошибка Telegram: {telegram_error}', exc_info=True)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'

            if message != last_message:
                with suppress(Exception):
                    send_message(bot, message)
                    last_message = message

            logger.error(message, exc_info=True)

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
