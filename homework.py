from http import HTTPStatus
import logging
import os
import requests
import time

from dotenv import load_dotenv
from telebot import TeleBot


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
    '%(asctime)s - %(funcName)s - [%(levelname)s] - %(message)s'
)
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger.addHandler(handler)


def check_tokens() -> bool:

    """
    Проверяет доступность переменных окружения.
    Проверка токенов Практикума и
    Bot API, id чата получателя. Возвращает булево значение.
    """

    if all((PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)):
        logger.info('Проверка переменных окружения прошла успешно')
        return True
    else:
        message = (
            'Отсутсвуют переменные окружения:'
            f'PRACTICUM TOKEN: {bool(PRACTICUM_TOKEN)}'
            f'TELEGRAM TOKEN: {bool(TELEGRAM_TOKEN)}'
            f'TELEGRAM CHAT ID: {bool(TELEGRAM_CHAT_ID)}'
        )
        logger.critical(message)
        return False


def send_message(bot: TeleBot, message: str) -> None:

    """
    Отправляет сообщение в Telegram-чат.
    Принимает на вход два параметра:
    экземпляр класса TeleBot и строку с текстом сообщения.
    """

    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug(f'Сообщение отправлено. {message}')

    except Exception:
        message = 'Ошибка отправки сообщения'
        logger.error(message)


def get_api_answer(timestamp: int) -> dict:

    """
    Делает запрос к единственному эндпоинту API-сервиса.
    В качестве параметра в функцию передаётся временная метка.
    В случае успешного запроса должна вернуть ответ API, приведя его из
    формата JSON к типам данных Python.
    """

    try:
        homework_statuses = requests.get(ENDPOINT,
                                         headers=HEADERS,
                                         params={'from_date': timestamp})
        if homework_statuses.status_code != HTTPStatus.OK:
            raise homework_statuses.raise_for_status()

    except requests.RequestException as error:
        message = f'Эндпоинт API недоступен: {error}'
        logger.error(message)
        raise Exception(message)

    return homework_statuses.json()


def check_response(response: dict) -> list:

    """
    Проверяет ответ API на соответствие документации.
    В качестве параметра функция получает ответ API,
    приведённый к типам данных Python.
    """

    if isinstance(response, dict):
        try:
            homeworks = response['homeworks']

        except KeyError as error:
            message = f'В ответе отсутсвует ключ {error}'
            logger.error(message)
            raise KeyError(message)

        else:
            if isinstance(homeworks, list):
                return homeworks
            else:
                raise TypeError('Ответ не содержит домашних работ')
    else:
        raise TypeError('Ответ не содержит словарь')


def parse_status(homework: dict) -> str:

    """
    Извлекает из информации о конкретной домашней работе статус этой работы.
    В качестве параметра функция получает только один элемент
    из списка домашних работ. В случае успеха функция возвращает
    подготовленную для отправки в Telegram строку, содержащую один из
    вердиктов словаря HOMEWORK_VERDICTS
    """

    try:
        homework_name = homework['homework_name']

    except KeyError as error:
        message = f'Ключ {error} отсутсвует в домашней работе'
        logger.error(message)
        raise KeyError(message)

    try:
        verdict = HOMEWORK_VERDICTS[homework['status']]

    except KeyError as error:
        message = f'{error}. Неизвестный статус домашней работы'
        logger.error(message)
        raise KeyError(message)

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():

    """Основная логика работы бота."""

    if not check_tokens():
        return None

    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())

    last_homework = None
    last_error = None

    while True:
        try:
            homework_statuses = get_api_answer(timestamp - RETRY_PERIOD)
            homework = check_response(homework_statuses)

            if (
                homework and (homework != last_homework)
            ):
                message = parse_status(homework[0])
                send_message(bot, message)
                last_homework = homework
            else:
                logger.debug('Статус домашней работы не изменился')

            timestamp = homework_statuses.get('current_date')
            time.sleep(RETRY_PERIOD)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'

            if str(error) != last_error:
                send_message(bot, message)
                last_error = str(error)

            logger.error(message)
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
