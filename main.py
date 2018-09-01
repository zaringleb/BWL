import json
import logging
import os
import requests

from telegram.ext import CommandHandler, MessageHandler, Filters, Updater, JobQueue
from telegram import Bot, ReplyKeyboardMarkup
#  https://github.com/python-telegram-bot/python-telegram-bot

from word_tools import UserWordList, OxfordApi


dir_path = os.path.dirname(os.path.realpath(__file__))


class BotWordsLearner:
    def __init__(self, path, token, logger, config, api):
        self.path = path
        self.token = token
        self.logger = logger
        self.config = config
        self.api = api
        self.users_word_lists = {}

    def start(self, bot, update):
        self._log_update(update)
        username = update.message.from_user.username
        self.users_word_lists[username] = UserWordList(
            username, os.path.join(self.path, self.config["user_data_dir"]), self.logger,
            self.config['word_list'])
        bot.sendMessage(chat_id=update.message.chat_id, text="Please, send me file")

    def help(self, bot, update):
        with open(os.path.join(self.path, self.config["help_filename"])) as f:
            text = f.read()
        bot.sendMessage(chat_id=update.message.chat_id, text=text.format(**self.config['talk']))
        self._log_update(update)

    def stat(self, bot, update):
        self._log_update(update)
        username = update.message.from_user.username
        reply = self.users_word_lists[username].get_stat()
        bot.sendMessage(chat_id=update.message.chat_id, text=reply)

    def save_to_disk(self):
        for username in self.users_word_lists:
            self.users_word_lists[username].save_to_file()

    def load_from_disk(self):
        self.logger.info("Start to load user data from disk")
        for username in os.listdir(os.path.join(self.path, self.config["user_data_dir"])):
            self.users_word_lists[username] = UserWordList(
                username, os.path.join(self.path, self.config["user_data_dir"]),
                self.logger, self.config['word_list'])
            self.users_word_lists[username].load_from_file()
            self.logger.info("Load {} words for user: {}".format(
                len(self.users_word_lists[username].words), username)
            )

    def error(self, _, update, error):
        self.logger.error('Update {} caused error {}'.format(update, error))

    def talk(self, bot, update):
        self._log_update(update)

        talk = self.config['talk']

        message = update.message.text.lower()
        username = update.message.from_user.username

        if self.users_word_lists[username].words:
            if message in talk.values():
                if message == talk['yes']:
                    self.users_word_lists[username].current_word.success()
                elif message == talk['no']:
                    self.users_word_lists[username].current_word.unsuccess()
                elif message == talk['delete']:
                    answer = self.users_word_lists[username].delete_current_word()
                    bot.sendMessage(chat_id=update.message.chat_id, text=answer)
                elif message == talk['next']:
                    pass
                reply = self.users_word_lists[username].choose()
            else:
                reply = 'Sorry, I don`t understand you, try /help'
        else:
            reply = 'Please send me file with words!'
        bot.sendMessage(chat_id=update.message.chat_id, text=reply)

    def document_load(self, bot, update):
        username = update.message.from_user.username
        self.logger.info("FROM: {}, loading document".format(username))
        json_url = '{}/bot{}/getFile?file_id={}'.format(
            self.config["TELEGRAM_API"], self.token, update.message.document['file_id']
        )
        answer = requests.get(json_url)

        file_url = '{}/file/bot{}/{}'.format(
            self.config["TELEGRAM_API"], self.token, json.loads(answer.text)['result']['file_path']
        )
        result = requests.get(file_url)
        added_words = self.users_word_lists[username].load_new_words(result.text, self.api)

        bot.sendMessage(chat_id=update.message.chat_id,
                        text="Number of added words: {}".format(len(added_words)))
        bot.sendMessage(chat_id=update.message.chat_id,
                        text="\n".join(map(str, sorted(added_words))))
        bot.sendMessage(chat_id=update.message.chat_id,
                        text=self.users_word_lists[username].choose())

        self.keyboard(bot, update)

    def _log_update(self, update):
        self.logger.info('FROM: {} TEXT: {} CHART_ID: {}'.format(
            update.message.from_user.username,
            update.message.text.encode('UTF-8'),
            update.message.chat_id)
        )

    def keyboard(self, _, update):
        self._log_update(update)
        reply_keyboard = [[self.config['talk']['yes'], self.config['talk']['no'],
                           self.config['talk']['next'], self.config['talk']['delete']],
                          ["/stat"]]
        update.message.reply_text("keyboard: ",
                                  reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                                                   one_time_keyboard=False))


def get_bot_token(token_path):
    with open(token_path) as f:
        return f.readline().strip()


def run_and_log(function_to_run, logger):
    def run(bot, job):
        logger.info("Start run {}".format(function_to_run))
        function_to_run()
        logger.info("Finish run {}".format(function_to_run))
    return run


def get_logger(file_log_name):
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(os.path.join(dir_path, file_log_name))
    fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s:%(message)s'))
    logger.addHandler(fh)
    return logger


def main():
    with open(os.path.join(dir_path, 'config.json')) as config_file:
        config = json.loads(config_file.read())['main']

    logger = get_logger(config["log_filename"])

    api = OxfordApi(config['api'], logger)

    bot_words_learner = BotWordsLearner(dir_path, get_bot_token(config["token_path"]), logger,
                                        config["bot_words_learner"], api)
    bot_words_learner.load_from_disk()

    job_queue = JobQueue(Bot(get_bot_token(config["token_path"])))
    job_queue.run_repeating(run_and_log(bot_words_learner.save_to_disk, logger), 60 * 60)
    job_queue.start()

    updater = Updater(token=bot_words_learner.token)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler('start', bot_words_learner.start))
    dispatcher.add_handler(CommandHandler('help', bot_words_learner.help))
    dispatcher.add_handler(CommandHandler('stat', bot_words_learner.stat))
    dispatcher.add_handler(MessageHandler(Filters.text, bot_words_learner.talk))
    dispatcher.add_handler(MessageHandler(Filters.document, bot_words_learner.document_load))
    dispatcher.add_handler(CommandHandler('keyboard', bot_words_learner.keyboard))
    dispatcher.add_error_handler(bot_words_learner.error)

    updater.start_polling()
    updater.idle()
    logger.critical('Finish session\n')
    bot_words_learner.save_to_disk()
    api.cash.save()
    job_queue.stop()


if __name__ == '__main__':
    main()
