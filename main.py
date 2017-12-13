# -*- coding: utf-8 -*-

import os
import logging
import random
import json
import requests
import codecs
import time
from telegram.ext import CommandHandler
from telegram.ext import MessageHandler, Filters
from telegram.ext import Updater


WORDS_REMAINDER_COUNT = 5
TIME_BEFORE_REPEAT_INIT = 60*60*12
TIME_BEFORE_REPEAT_MULT = 4
USER_FILE_SUFFIX = ".txt"
TELEGRAM_API = "https://api.telegram.org"
dir_path = os.path.dirname(os.path.realpath(__file__))


class Word():
    def __init__(self, value, events=None):
        self.value = value
        if events is None:
            self.events = []
        else:
            self.events = events

    def __str__(self):
        return self.value

    def __repr__(self):
        if self.events:
            return 'Word(value=\'{}\', events={})'.format(self.value, self.events)
        else:
            return 'Word(value=\'{}\')'.format(self.value)

    def create_event(self, eventtype):
        self.events.append({'time': int(time.time()), 'eventtype': eventtype})

    def success(self):
        self.create_event('success')

    def unsuccess(self):
        self.create_event('unsuccess')

    def get_last_success_time(self):
        for event in self.events[::-1]:
            if event['eventtype'] == 'success':
                return event['time']

    def number_of_success(self):
        return len([event for event in self.events if event['eventtype'] == 'success'])

    def last_is_success(self):
        if self.events:
            if self.events[-1]['eventtype'] == 'success':
                return True
        return False

class UserWordList():
    def __init__(self, username, filepath, logger):
        self.logger = logger
        self.username = username
        self.filepath = filepath
        self.words = []
        self.current_word = None

    def __len__(self):
        return len(self.words)

    def load_new_words(self, text):
        new_words = text.split('\n')
        new_words = set(new_words) - {str(word) for word in self.words}
        for one in new_words:
            self.words.append(Word(one))
        self.logger.info('user: {}, number of added words: {}'.format(
            self.username, len(new_words)))
        return len(new_words)

    def save_to_file(self):
        with codecs.open(os.path.join(self.filepath, self.username), 'w') as f_out:
            data = {"current_word": self.current_word.__repr__(), "words": [word.__repr__() for word in self.words]}
            f_out.write(json.dumps(data))

    def load_from_file(self):
        with codecs.open(os.path.join(self.filepath, self.username)) as f_in:
            data = json.loads(f_in.read())
            self.current_word = eval(data['current_word'])
            self.words = [eval(word) for word in data['words']]


    def choose(self):
        if not self.words:
            return "I need file from you to start :("
        current_time = int(time.time())
        available_words = []
        for word in self.words:
            if word.last_is_success():
                time_since_success = current_time - word.get_last_success_time()
                if time_since_success > (TIME_BEFORE_REPEAT_INIT *
                                             pow(TIME_BEFORE_REPEAT_MULT, word.number_of_success() - 1)):
                    available_words.append(word)
            else:
                available_words.append(word)

        if not available_words:
            self.logger.info('user: {} no more words!'.format(
                self.username))
            self.current_word = None
            return "Great job!\n For a moment you have learned everything, wait or send me more words."
        self.current_word = random.choice(available_words)
        self.logger.info('user: {} number of available words: {}, currend word: {}'.format(
                    self.username, len(available_words), self.current_word))
        return str(self.current_word)

class BotWordsLearner():
    def __init__(self, path, token, logger):
        self.path = path
        self.token = token
        self.logger = logger
        self.users_word_lists = {}

    def start(self, bot, update):
        self._log_update(update)
        username = update.message.from_user.username
        self.users_word_lists[username] = UserWordList(
            username, os.path.join(self.path, 'user_data'), self.logger)
        bot.sendMessage(chat_id=update.message.chat_id, text="Please, send me .txt file")

    def save_to_disk(self):
        for username in self.users_word_lists:
            self.users_word_lists[username].save_to_file()

    def load_from_disk(self):
        self.logger.info("Start to load user data from disk")
        for username in os.listdir(os.path.join(self.path, 'user_data')):
            self.users_word_lists[username] = UserWordList(
            username, os.path.join(self.path, 'user_data'), self.logger)
            self.users_word_lists[username].load_from_file()
            self.logger.info("Load {} words for user: {}".format(len(self.users_word_lists[username].words), username))

    def error(self, bot, update, error):
        self.logger.error('Update "%s" caused error "%s"' % (update, error))

    def talk(self, bot, update):
        self._log_update(update)

        message = update.message.text
        username = update.message.from_user.username

        if self.users_word_lists[username].current_word:
            if message.lower() == 'y':
                self.users_word_lists[username].current_word.success()
            elif message.lower() == 'n':
                self.users_word_lists[username].current_word.unsuccess()
            message = self.users_word_lists[username].choose()
        else:
            message = 'Please send me file with words!'
        bot.sendMessage(chat_id=update.message.chat_id, text=message)

    def document_load(self, bot, update):
        self._log_update(update)

        username = update.message.from_user.username
        json_url = '{}/bot{}/getFile?file_id={}'.format(TELEGRAM_API, self.token, update.message.document['file_id'])
        answer = requests.get(json_url)

        file_url = '{}/file/bot{}/{}'.format(TELEGRAM_API, self.token, json.loads(answer.text)['result']['file_path'])
        result = requests.get(file_url)
        #with codecs.open(os.path.join(dir_path, username + '.txt'), 'w', encoding='utf-8') as f_out:
        #    f_out.write(result.text)
        number_of_uploaded = self.users_word_lists[username].load_new_words(result.text)

        bot.sendMessage(chat_id=update.message.chat_id, text="New words: {}".format(number_of_uploaded))
        bot.sendMessage(chat_id=update.message.chat_id, text=self.users_word_lists[username].choose())

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

    bot_words_learner = BotWordsLearner(dir_path, get_bot_token(), logger)
    bot_words_learner.load_from_disk()

    updater = Updater(token=bot_words_learner.token)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler('start', bot_words_learner.start))
    dispatcher.add_handler(MessageHandler(Filters.text, bot_words_learner.talk))
    dispatcher.add_handler(MessageHandler(Filters.document, bot_words_learner.document_load))
    dispatcher.add_error_handler(bot_words_learner.error)

    updater.start_polling()
    updater.idle()
    logger.critical('Finish session\n')
    bot_words_learner.save_to_disk()

if __name__ == '__main__':
    main()
