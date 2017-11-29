# -*- coding: utf-8 -*-

import os
import logging
import random
import json
import requests
import codecs
from collections import defaultdict
from telegram.ext import CommandHandler
from telegram.ext import MessageHandler, Filters
from telegram.ext import Updater


WORDS_REMAINDER_COUNT = 5
TELEGRAM_API = "https://api.telegram.org"
dir_path = os.path.dirname(os.path.realpath(__file__))


class BotWordsLearner():
    def __init__(self, filename, token, logger):
        self.words = defaultdict(list)
        self.current_word = defaultdict(str)
        self.token = token
        self.logger = logger

    def start(self, bot, update):
        self._log_update(update)
        bot.sendMessage(chat_id=update.message.chat_id, text="Please, send me file")

    def error(self, bot, update, error):
        self.logger.error('Update "%s" caused error "%s"' % (update, error))

    def talk(self, bot, update):
        self._log_update(update)

        message = update.message.text
        username = update.message.from_user.username

        if message.lower() == 'y':
            if self.current_word[username]:
                self.words[username].remove(self.current_word[username])
                if len(self.words[username]) % WORDS_REMAINDER_COUNT == 0:
                    bot.sendMessage(chat_id=update.message.chat_id, text=len(self.words[username]))
        bot.sendMessage(chat_id=update.message.chat_id, text=self._get_new_word(username))

    def document_load(self, bot, update):
        self._log_update(update)

        username = update.message.from_user.username
        json_url = '{}/bot{}/getFile?file_id={}'.format(TELEGRAM_API, self.token, update.message.document['file_id'])
        answer = requests.get(json_url)

        file_url = '{}/file/bot{}/{}'.format(TELEGRAM_API, self.token, json.loads(answer.text)['result']['file_path'])
        result = requests.get(file_url)
        with codecs.open(os.path.join(dir_path, username + '.txt'), 'w', encoding='utf-8') as f_out:
            f_out.write(result.text)

        self._restart(username)
        bot.sendMessage(chat_id=update.message.chat_id, text="New words: {}".format(len(self.words[username])))
        bot.sendMessage(chat_id=update.message.chat_id, text=self._get_new_word(username))

    def _restart(self, username):
        self.words[username] = self.get_words(os.path.join(dir_path, username + '.txt'))
        self.current_word[username] = None


    def _get_new_word(self, username):
        if self.words[username]:
            new_word = random.choice(self.words[username])
            self.current_word[username] = new_word
            return new_word
        else:
            return 'No more words!'

    def get_words(self, filename):
        with open(filename) as f:
            return [line.strip() for line in f.readlines()]

    def _log_update(self, update):
        self.logger.info('FROM: {} TEXT: {} CHART_ID: {}'.format(update.message.from_user.username,
                                                                 update.message.text.encode('UTF-8'),
                                                                 update.message.chat_id))


def get_bot_token():
    with open('/home/zaringleb/.chip_token') as f:
        return f.readline().strip()


def main():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(os.path.join(dir_path, 'bot.log'))
    fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s:%(message)s'))
    logger.addHandler(fh)

    bot_words_learner = BotWordsLearner(os.path.join(dir_path), get_bot_token(), logger)

    updater = Updater(token=bot_words_learner.token)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler('start', bot_words_learner.start))
    dispatcher.add_handler(MessageHandler(Filters.text, bot_words_learner.talk))
    dispatcher.add_handler(MessageHandler(Filters.document, bot_words_learner.document_load))
    dispatcher.add_error_handler(bot_words_learner.error)

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
