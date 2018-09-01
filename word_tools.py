# -*- coding: utf-8 -*-

import os
import random
import json
import codecs
import time
import requests
from collections import Counter


class Word():
    success_event = "success"
    unsuccess_event = "unsuccess"

    def __init__(self, value, events=None, frequency=None):
        self.value = value
        self.frequency = frequency
        if events is None:
            self.events = []
        else:
            self.events = events

    def __str__(self):
        return self.value

    def __repr__(self):
        if self.events:
            return 'Word(value=\'{}\', events={}, frequency={})'.format(self.value, self.events, self.frequency)
        else:
            return 'Word(value=\'{}\', frequency={})'.format(self.value, self.frequency)

    def create_event(self, eventtype):
        self.events.append({'time': int(time.time()), 'eventtype': eventtype})

    def success(self):
        self.create_event(self.success_event)

    def unsuccess(self):
        self.create_event(self.unsuccess_event)

    def get_last_success_time(self):
        for event in self.events[::-1]:
            if event['eventtype'] == self.success_event:
                return event['time']

    def get_last_unsuccess_time(self):
        for event in self.events[::-1]:
            if event['eventtype'] == self.unsuccess_event:
                return event['time']

    def number_of_success(self):
        return len([event for event in self.events if event['eventtype'] == self.success_event])

    def last_is_success(self):
        if self.events:
            if self.events[-1]['eventtype'] == self.success_event:
                return True
        return False

    def is_new(self):
        if not self.events:
            return True
        return False


class UserWordList():
    def __init__(self, username, filepath, logger, config):
        self.logger = logger
        self.username = username
        self.filepath = filepath
        self.config = config
        self.words = []
        self.current_word = None
        self.banned_words = []
        self.low_frequency = []

    def __len__(self):
        return len(self.words)

    def is_ascii(self, value):
        try:
            value.encode('ascii')
            return True
        except UnicodeEncodeError:
            return False

    def load_new_words(self, text, api):
        new_words = [one.strip() for one in text.split('\n') if one.strip()]
        # non_ascii_words = [one for one in new_words if not self.is_ascii(one)]
        # self.logger.info('user: {} not add {} non ascii words'.format(self.username, len(non_ascii_words)))
        new_words = [one for one in new_words if self.is_ascii(one)]
        new_words = set(new_words) - {str(word) for word in self.words} - {str(word) for word in self.banned_words}
        added_words = []
        for one in new_words:
            result = api.get_root_form_and_frequency(one)
            if result:
                root_from, frequency = result
                if root_from not in {str(word) for word in self.words} and root_from not in {str(word) for word in self.banned_words}:
                    word = Word(root_from, frequency=frequency)
                    if frequency >= 1:
                        self.words.append(word)
                        added_words.append(word)
                    else:
                        self.low_frequency.append(word)
        self.logger.info('user: {}, number of added words: {}'.format(
            self.username, len(new_words)))
        return added_words

    def save_to_file(self):
        with codecs.open(os.path.join(self.filepath, self.username), 'w') as f_out:
            data = {"current_word": self.current_word.__repr__() if self.current_word else "None",
                    "words": [word.__repr__() for word in self.words],
                    "banned_words": [word.__repr__() for word in self.banned_words],
                    "low_frequency": [word.__repr__() for word in self.low_frequency]}
            f_out.write(json.dumps(data))

    def load_from_file(self):
        with codecs.open(os.path.join(self.filepath, self.username)) as f_in:
            data = json.loads(f_in.read())
            self.current_word = eval(data['current_word'])
            self.words = [eval(word) for word in data['words']]
            self.banned_words = [eval(word) for word in data.get('banned_words', [])]
            self.low_frequency = [eval(word) for word in data.get('low_frequency', [])]

    def choose(self):
        if not self.words:
            return "I need file from you to start :("
        current_time = int(time.time())
        available_words = []
        new_available_words = []
        for word in self.words:
            if word.last_is_success():
                time_since_success = current_time - word.get_last_success_time()
                if time_since_success > min((eval(self.config["TIME_BEFORE_REPEAT_INIT"]) *
                                            pow(eval(self.config["TIME_BEFORE_REPEAT_MULT"]),
                                                word.number_of_success() - 1)),
                                        eval(self.config["TIME_BEFORE_REPEAT_MAX"])):
                    available_words.append(word)
            elif word.is_new():
                new_available_words.append(word)
            else:
                time_since_unsuccess = current_time - word.get_last_unsuccess_time()
                if time_since_unsuccess > eval(self.config["TIME_BEFORE_REPEAT_WRONG"]):
                    available_words.append(word)

        if len(available_words) < self.config["MIN_AVAILABLE_WORDS"]:
            available_words.extend(new_available_words[:self.config["MIN_AVAILABLE_WORDS"] - len(available_words)])

        if not available_words:
            self.logger.info('user: {} no more words!'.format(
                self.username))
            self.current_word = None
            return "Great job!\n For a moment you have learned everything, wait or send me more words."
        self.current_word = random.choice(available_words)
        self.logger.info('user: {} number of available words: {}, currend word: {}'.format(
                    self.username, len(available_words), self.current_word))
        return str(self.current_word)

    def delete_current_word(self):
        self.banned_words.append(self.current_word)
        self.words.remove(self.current_word)
        return '{} was deleted'.format(self.current_word)

    def get_stat(self, period=None):
        stat = Counter()
        for word in self.words:
            if word.last_is_success():
                stat['repeat'] += 1
            if word.is_new():
                stat['new'] += 1
            if (not word.is_new()) and (not word.last_is_success()):
                stat['to learn'] += 1

        return ", ".join(["{}: {}".format(key, stat[key]) for key in sorted(stat.keys())])

    def add_word(self, value):
        self.words.append(Word(value))
        return 'word {} was added'.format(value)


class OxfordApi(object):
    def __init__(self, config, logger):
        self.app_id = config['app_id']
        with open(config['app_key_path']) as app_key_file:
            self.app_key = app_key_file.read().strip()
        self.cash = Cash(config['cash_file'])
        self.logger = logger
        self.language = 'en'
        self.url = "https://od-api.oxforddictionaries.com:443/api/v1/"

    def _get_root_form(self, word):
        url = self.url + 'inflections/' + self.language + '/' + word.lower()
        r = requests.get(url, headers={'app_id': self.app_id, 'app_key': self.app_key})
        try:
            result = r.json()['results'][0]['lexicalEntries'][0]['inflectionOf'][0]['id']
        except Exception:
            self.logger.error("api: word={}".format(word))
            result = None
        return result

    def _get_frequency(self, word):
        url = self.url + 'stats/frequency/word/' + self.language + '/?corpus=nmc&lemma=' + word.lower()
        r = requests.get(url, headers={'app_id': self.app_id, 'app_key': self.app_key})
        try:
            result = r.json()['result']['normalizedFrequency']
        except Exception:
            self.logger.error("api: word={}".format(word))
            result = None
        return result

    def _get_root_form_and_frequency(self, word):
        root_from = self._get_root_form(word)
        if root_from:
            frequency = self._get_frequency(root_from)
            if frequency:
                return root_from, frequency

    def get_root_form_and_frequency(self, word):
        return self.cash.get(word, self._get_root_form_and_frequency)


class Cash(object):
    def __init__(self, filename):
        self.filename = filename
        if os.path.exists(self.filename):
            with open(self.filename) as in_file:
                self.content = json.load(in_file)
        else:
            self.content = {}

    def save(self):
        with open(self.filename, 'w') as out_file:
            json.dump(self.content, out_file)

    def get(self, key, func):
        if key in self.content:
            return self.content[key]
        else:
            value = func(key)
            self.content[key] = value
            return value