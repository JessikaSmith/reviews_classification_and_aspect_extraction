# domain_name.train_data

import pymystem3
from tqdm import tqdm

from nltk.stem import PorterStemmer, WordNetLemmatizer
import nltk
from nltk.corpus import wordnet as wn
from nltk.corpus import stopwords
from keras.preprocessing.text import Tokenizer
from keras.preprocessing import sequence
from classifcation.word2vec_preparation import w2v_model
from sklearn.preprocessing import OneHotEncoder, LabelEncoder

import json

# nltk.download('stopwords')
# nltk.download('averaged_perceptron_tagger')
# nltk.download('wordnet')

import numpy as np
import re


def convert_tag(tag):
    if tag in ['NN', 'NNS', 'NNP', 'NNPS']:
        return wn.NOUN
    if tag in ['VB', 'VBD', 'VBG', 'VBN', 'VBP', 'VBZ']:
        return wn.VERB
    if tag in ['RB', 'RBR', 'RBS']:
        return wn.ADV
    if tag in ['JJ', 'JJR', 'JJS']:
        return wn.ADJ
    return 'trash'


def process_punkt(text):
    for char in ['.', '"', ',', '(', ')', '!', '?', ';', ':']:
        text = text.replace(char, ' ')
    return text


def clean_text(text):
    wordnet_lemmatizer = WordNetLemmatizer()
    stop = stopwords.words("english")
    text = text.strip().lower()
    text = process_punkt(text)
    tokens = re.split("[\s;,]", text)
    tokens = [x for x in tokens if x.isalpha()]
    tokens = [x for x in tokens if len(x) > 3]
    tokens_res = []
    res = nltk.pos_tag(tokens)
    for i in res:
        if convert_tag(i[1]) != 'trash' and i[0] not in stop:
            tokens_res.append(wordnet_lemmatizer.lemmatize(i[0], convert_tag(i[1])))
    return tokens_res


def process_similarity(w2v_model, word):
    try:
        sim = w2v_model.findSynonyms(word, 1).take(1)[0][0]
    except:
        return None
    return sim


def create_document_with_similarity_replacement():
    raise NotImplementedError


def tokens_to_text(tokens):
    return " ".join(tokens)


def text_to_tokens(text):
    return text.split()


def text_len(text):
    return len(text)


def batch_iterator(data, batch_size, num_epoch, shuffle=True):
    data = np.array(data)
    data_size = len(data)
    batches_per_epoch = int((len(data) - 1) / batch_size) + 1
    for epoch in range(num_epoch):
        if shuffle:
            shuffle_indicis = np.random.permutation(np.arange(data_size))
            shuffled_data = data[shuffle_indicis]
        else:
            shuffled_data = data
        for i in range(batches_per_epoch):
            start = i * batch_size
            end = min((i + 1) * batch_size, data_size)
            yield shuffled_data[start:end]


# TODO: add simple binary vector representation of sentences
def prepare_binary_vectors(train_x, test_x):
    raise NotImplementedError


def prepare_input_sequences(train_x, test_x, type, max_len=0, max_num_of_words=10000):
    if type == 'w2v_mean':
        model = w2v_model()
        model.model_from_file('amazon')
        train_x, test_x = _w2v_mean_preparation(train_x, test_x, model)
    if type == 'freq_seq':
        train_x, test_x = _freq_seq_preparation(train_x, test_x, max_len, max_num_of_words=max_num_of_words)
    if type == 'bow':
        train_x, test_x = _bow_preparation(train_x, test_x, max_len)
    return train_x, test_x


def _w2v_mean_preparation(train_x, test_x, w2v_model):
    new_train_x = []
    new_test_x = []
    print('Preparing w2v_mean vectors...')
    for sentence in tqdm(test_x):
        new_test_x.append(w2v_model.get_w2v_mean(sentence))
    print('Test set: success')
    for sentence in tqdm(train_x):
        new_train_x.append(w2v_model.get_w2v_mean(sentence))
    print('Train set: success')
    np_train = np.array(new_train_x)
    np_test = np.array(new_test_x)
    return np.squeeze(np_train, axis=1), np.squeeze(np_test, axis=1)


def _freq_seq_preparation(train_x, test_x, max_len, max_num_of_words):
    print('Tokenizer starts... ')
    tokenizer = Tokenizer(num_words=max_num_of_words)
    tokenizer.fit_on_texts(train_x + test_x)
    print('Fitting is done')
    x_train = tokenizer.texts_to_sequences(train_x)
    x_test = tokenizer.texts_to_sequences(test_x)
    # transforms a list of num_samples sequences into 2D np.array shape (num_samples, num_timesteps)
    x_train = sequence.pad_sequences(x_train, maxlen=max_len, padding='post', truncating='post')
    print('Size of training set: %i' % len(x_train))
    x_test = sequence.pad_sequences(x_test, maxlen=max_len, padding='post', truncating='post')
    print('Size of test set: %i' % len(x_test))
    return x_train, x_test


# simple document representation => sum of one-hot text vectors
def _bow_preparation(train_x, test_x, max_len):
    le = LabelEncoder(train_x + test_x)
    le.fit()
    # change size to max_len
    enc = OneHotEncoder()
    enc.fit(train_x + test_x)
    return enc.transform(train_x).toarray(), enc.transform()

    # TODO: search for similar words


ALPHABET = 'abcdefghijklmnopqrstuvwxyz '


# simplified variant without punctuation

def get_sequence(dataset, max_len):
    all_data = []
    for row in dataset:
        # data = np.ones(SEQUENE_MAX_LEN)*68
        all_data.append(char2vec(row, max_len))
    return np.array(all_data)


def char2vec(text, max_len):
    data = np.zeros(max_len)
    char_dict = {}
    for i, c in enumerate(ALPHABET):
        char_dict[c] = i + 1
    for i in range(0, len(text)):
        if i > max_len:
            return data
        elif text[i] in char_dict:
            data[i] = char_dict[text[i]]
    return data
