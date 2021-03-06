# BUG: occasionally causes TypeError in __del__: 'NoneType' object is not callable
import tensorflow as tf

config = tf.ConfigProto()
config.gpu_options.visible_device_list = "0"
config.gpu_options.per_process_gpu_memory_fraction = 0.7
config.allow_soft_placement = True
config.gpu_options.allow_growth = True
session = tf.Session(config=config)

from keras.backend.tensorflow_backend import set_session

set_session(session)

from keras.layers import Input, Dense, \
    Embedding, Conv2D, MaxPool2D, Reshape, \
    Flatten, Dropout, Concatenate, Convolution1D, MaxPooling1D, \
    LSTM, RepeatVector, Activation, Conv1D, GlobalMaxPooling1D, \
    BatchNormalization, Lambda
from keras.engine import Layer, InputSpec
from keras.optimizers import Adam, SGD
from keras.models import Model, Sequential
import logging
from keras import losses
from keras import metrics
from keras import backend as k
from keras.callbacks import ModelCheckpoint, ReduceLROnPlateau, EarlyStopping, TensorBoard
from tqdm import tqdm
import os
import numpy as np
from keras.utils import Sequence, to_categorical
# import skopt
import tensorflow as tf
from tqdm import tqdm
import time
from keras.preprocessing import sequence
from keras.preprocessing.text import Tokenizer
from sklearn.model_selection import StratifiedKFold
from gensim.models import Word2Vec
from classifcation.vis_tools.vis import *

IO_DIR = 'data_dir'

# configuration


# TODO: add logging info messages
logger = logging.getLogger(__name__)


def save_model_to_json(model, fname):
    model_json = model.to_json()
    with open('%s/%s.json' % (IO_DIR, fname), "w") as json_file:
        json_file.write(model_json)
    print("Model saved as json")


# data is passed as np array
class BatchGenerator(Sequence):
    def __init__(self, data, batch_size=64, labels=None, num_classes=5):
        self.labels = labels
        self.data = data
        self.num_classes = num_classes
        self.batch_size = batch_size
        self.indexes = np.arange(0, self.data.shape[0])

    def __len__(self):
        return int(np.ceil(len(self.data) / self.batch_size))

    def __getitem__(self, index):
        part_indixes = self.indexes[index * self.batch_size:(index + 1) * self.batch_size]
        X = self.data[part_indixes]
        if self.labels is not None:
            pass


def sentence_batch_generator(data, batch_size=64, num_classes=5, labels=None):
    n_batch = int(np.ceil(len(data) / batch_size))
    batch_count = 0
    # shuffle with labels
    # np.random.shuffle(data)
    indices = np.arange(0, data.shape[0])

    while True:
        if batch_count == n_batch:
            np.random.shuffle(data)
            batch_count = 0

        batch = data[batch_count * batch_size:(batch_count + 1) * batch_size]
        batch_count += 1
        yield batch, y


def max_margin_loss(y_true, y_pred):
    return k.mean(y_pred)


def get_callbacks(name_weights, patience_lr):
    checkpoint_save = ModelCheckpoint(name_weights, save_best_only=True, monitor='val_loss', mode='min')
    reduce_lr_loss = ReduceLROnPlateau(monitor='loss', factor=0.1, patience=patience_lr,
                                       verbose=1, epsilon=1e-4, mode='min')


def _get_vocabulary_inv(vocab):
    vocab_inv = {}
    for w, ind in vocab.items():
        vocab_inv[ind] = w
    return vocab_inv


class Base_Model:

    def create_model(self, *args):
        raise NotImplementedError

    def train_model(self, *args):
        raise NotImplementedError

    def predict(self, *args):
        raise NotImplementedError


class KMaxPooling(Layer):

    def __init__(self, k=1, sorted=True, **kwargs):
        super().__init__(**kwargs)
        self.input_spec = InputSpec(ndim=3)
        self.k = k
        self.sorted = sorted

    def compute_output_shape(self, input_shape):
        return (input_shape[0], self.k, input_shape[2])

    def call(self, inputs):
        swapped_dim_inputs = tf.transpose(inputs, [0, 2, 1])

        high_k = tf.nn.top_k(swapped_dim_inputs, k=self.k, sorted=self.sorted)[0]

        return tf.transpose(high_k, [0, 2, 1])


# TODO: perform model optimization

class CNN_model(Base_Model):

    def __init__(self):
        self.model = None

    def create_model(self, vocabulary, max_sentence_len=0, embedding_dim=300,
                     num_conv_filters=512, filter_size=None, drop=0.5):

        # TODO: state hyperparams explicitly
        NUM_FILTERS = 10
        DROPOUT_PROB = (0.5, 0.8)
        HIDDEN = 50

        if filter_size is None:
            filter_size = [3, 4, 5]

        vocab_size = len(vocabulary)
        inputs = Input(shape=(max_sentence_len,), dtype='int32', name='reviews_input')
        word_embedding = Embedding(input_dim=vocab_size, output_dim=embedding_dim,
                                   input_length=max_sentence_len, name='word_embedding')(inputs)

        # TODO: thy other activation function

        z = Dropout(DROPOUT_PROB[0])(word_embedding)

        # convolutional section
        conv_list = []
        # TODO: check conv2d
        for sz in filter_size:
            conv = Convolution1D(filters=NUM_FILTERS, kernel_size=sz, padding="valid",
                                 activation="relu", strides=1)(z)
            conv = MaxPooling1D(pool_size=2)(conv)
            conv = Flatten()(conv)
            conv_list.append(conv)

        flatten = Concatenate()(conv_list) if len(conv_list) > 1 else conv_list[0]
        dropout = Dropout(DROPOUT_PROB[1])(flatten)

        output = Dense(HIDDEN, activation='relu')(dropout)

        # TODO: remove hardcore
        model_output = Dense(5, activation="sigmoid")(output)
        self.model = Model(inputs=inputs, outputs=model_output)

    # Convolutional Neural Networks for Sentence Classification
    def create_simple_model(self, vocab_size, max_len, emb_dim,
                            filters=None, filter_size=100):
        if not filters:
            filters = [3, 5, 7]
        input_shape = (max_len,)
        inputs = Input(shape=input_shape, dtype='int32', name='inputs')
        word_emb = Embedding(vocab_size, emb_dim, input_length=max_len, name='embeddings')(inputs)
        dropout = Dropout(0., name='dropout_emb')(word_emb)
        conv_list = []
        for filter in filters:
            # check here
            conv = Convolution1D(filters=filter_size, kernel_size=filter, padding="valid",
                                 activation="relu", name='conv_' + str(filter))(dropout)
            mp = MaxPooling1D(pool_size=max_len - filter + 1, name='maxpool_' + str(filter))(conv)
            flat = Flatten()(mp)
            conv_list.append(flat)
        # flatten = Concatenate()(conv_list) if len(conv_list) > 1 else conv_list[0]
        merged = Concatenate()(conv_list)
        dropout_2 = Dropout(0., name='dropout')(merged)
        model_output = Dense(5, activation='sigmoid')(dropout_2)
        self.model = Model(inputs=inputs, outputs=model_output)
        print(self.model.summary())

    def train_simple_model(self):
        raise NotImplementedError

    def create_imdb_model(self):
        max_features = 10000
        maxlen = 500
        embedding_dims = 50
        filters = 250
        kernel_size = 3
        hidden_dims = 250
        print('Build model...')
        self.model = Sequential()
        self.model.add(Embedding(max_features,
                                 embedding_dims,
                                 input_length=maxlen))
        self.model.add(Dropout(0.2))
        self.model.add(Conv1D(filters,
                              kernel_size,
                              padding='valid',
                              activation='relu',
                              strides=1))
        self.model.add(GlobalMaxPooling1D())

        # Add a vanilla hidden layer:
        self.model.add(Dense(hidden_dims))
        self.model.add(Dropout(0.2))
        self.model.add(Activation('relu'))
        self.model.add(Dense(1))
        self.model.add(Activation('sigmoid'))
        self.model.compile(loss='binary_crossentropy',
                           optimizer='adam',
                           metrics=['accuracy'])

    def fit_imdb_model(self, train_x, train_y, test_x, test_y):
        batch_size = 32
        epochs = 2
        self.model.fit(train_x, train_y,
                       batch_size=batch_size,
                       epochs=epochs,
                       validation_data=(test_x, test_y))

    def _init_weights(self, domain_name, vocab_inv):

        embedding_model = Word2Vec.load('%s/%s/w2v_embedding' % (IO_DIR, domain_name))
        embedding_weights = {key: embedding_model[word] if word in embedding_model else
        np.random.uniform(-0.25, 0.25, embedding_model.vector_size)
                             for key, word in vocab_inv.items()}
        weights = np.array([v for v in embedding_weights.values()])
        embedding_layer = self.model.get_layer("word_embedding")
        embedding_layer.set_weights([weights])

    def train_model(self, x_train, y_train, x_test, y_test, vocab, epochs=100, batch_size=100, max_len=0,
                    max_num_of_words=1000):
        checkpoint = ModelCheckpoint('weights.{epoch:03d}-{val_acc:.4f}.hdf5', monitor='val_acc',
                                     verbose=1, save_best_only=True, mode='auto')
        min_loss = float('inf')
        # TODO: tune optimizer parameters
        self.model.compile(optimizer=Adam(lr=1e-4), loss=losses.categorical_crossentropy,
                           metrics=['accuracy'])
        print(self.model.summary())

        sen_gen = sentence_batch_generator(x_train, batch_size)

        vocab_inv = {}
        for w, ind in vocab.items():
            vocab_inv[ind] = w

        batches_num_epoch = 1000
        print('Model is being trained...')
        for i in range(epochs):
            start = time.time()
            loss, max_margin_loss = 0., 0.
            for b in tqdm(range(batches_num_epoch)):
                sen_input = sen_gen.next()
                batch_loss, batch_max_margin_loss = self.model.train_on_batch(sen_input,
                                                                              np.ones((batch_size, 1)))
                loss += batch_loss / batches_num_epoch
                max_margin_loss += batch_max_margin_loss / batches_num_epoch
            total_time = time.time() - start
            if loss < min_loss:
                min_loss = loss
                word_emb = self.model.get_layer('word_embedding').W.get_value()
                word_emb = word_emb / np.linalg.norm(word_emb, axis=-1, keepdims=True)
                # TODO: remove domain name
                self.model.save_weights('%s/%s/model_param' % (IO_DIR, 'amazon'))

            print('Epoch %d, train %is' % (i, total_time))

        # self.model.fit(x_train, y_train, batch_size=batch_size, epochs=epochs, verbose=1,
        #                callbacks=[checkpoint], validation_data=(x_test, y_test))

    def simple_train(self, domain_name, vocab, x_train, y_train, x_test, y_test, max_len,
                     batch_size=32, num_epochs=10, max_num_of_words=20000):
        print('Training process has begun')
        checkpoint = ModelCheckpoint('weights.{epoch:03d}-{val_acc:.4f}.hdf5', monitor='val_acc',
                                     verbose=1, save_best_only=True, mode='auto')
        early_stop = EarlyStopping(monitor='val_acc', patience=5, mode='max')
        plot_losses = PlotLosses()
        callbacks_list = [checkpoint, early_stop, plot_losses]

        # TODO: tune optimizer parameters
        self.model.compile(optimizer=Adam(lr=1e-4), loss=losses.categorical_crossentropy,
                           metrics=['accuracy'])
        print(self.model.summary())

        vocab_inv = _get_vocabulary_inv(vocab)
        # self._init_weights(domain_name, vocab_inv)
        history = self.model.fit(x_train, y_train, batch_size=batch_size, epochs=num_epochs,
                                 validation_data=(x_test, y_test), verbose=1, callbacks=callbacks_list)

    def train_on_embeddings(self, embedding_type='w2v'):
        assert embedding_type in ['pretrained_w2v', 'w2v', 'glove']

    def predict(self):
        raise NotImplementedError


class CNN_2D(Base_Model):
    """
    Each sentence is represented as an image of shape (sent_num_of_words, embedding_dim)
    """

    def __init__(self):
        self.model = None

    def _reshape_data(self, data, labels, embedding_dim, w2v_model):
        # w2v_model
        # input = Input(shape=(embedding_dim, None, None))
        raise NotImplementedError

    def create_model(self, max_len, emb_dim, word_index, embedding_matrix):
        # np.zeros((5,), dtype=np.int) => array([0, 0, 0, 0, 0])
        inputs = Input(shape=(max_len,), dtype='int32', name='reviews_input')
        embedding_layer = Embedding(len(word_index) + 1, emb_dim, weights=[embedding_matrix],
                                    input_length=max_len, trainable=False)
        raise NotImplementedError


class LSTM_model(Base_Model):

    def __init__(self):
        # sequence_length =
        model = None

    # MAX_WORDS_TO_USE = 10000
    # VALIDATION_SPLIT = 0.2
    # EMBEDDING_DIM = 300

    # from keras.preprocessing.text import Tokenizer
    # tokenizer = Tokenizer(num_words=MAX_WORDS_TO_USE
    #

    def create_model(self, max_sentence_len, max_words, max_len):
        # TODO: difference max_sentence_len vs max_words
        inputs = Input(shape=(max_sentence_len,), name='inputs')
        embedding_layer = Embedding(max_words, 50, input_length=max_len)(inputs)
        layer = LSTM(64)(embedding_layer)
        layer = Activation('relu')(layer)
        layer = Dropout(0.5)(layer)
        layer = Dense(1, name='out_layer')(layer)
        self.model = Model(inputs=inputs, outputs=layer)

    # conv layer helps to speed up the computations
    def create_model_with_conv_layer(self, vocabulary_size, max_len, embedding_dim=200):
        model_conv = Sequential()
        model_conv.add(Embedding(vocabulary_size, embedding_dim, input_length=max_len))
        model_conv.add(Dropout(0.2))
        model_conv.add(Convolution1D(64, 5, activation='relu'))
        model_conv.add(MaxPooling1D(pool_size=4))
        model_conv.add(LSTM(100))
        model_conv.add(Dense(5, activation='sigmoid'))
        model_conv.compile(loss=losses.categorical_crossentropy, optimizer='adam', metrics=['accuracy'])
        print('Model summary')
        self.model = model_conv
        print(self.model.summary())

    def train_model(self, vocab, x_train, y_train, x_test, y_test, max_len,
                    batch_size=64, num_epochs=10, max_num_of_words=20000):
        print('Training process has begun')
        checkpoint = ModelCheckpoint('weights.{epoch:03d}-{val_acc:.4f}.hdf5', monitor='val_acc',
                                     verbose=1, save_best_only=True, mode='auto')
        early_stop = EarlyStopping(monitor='val_acc', patience=5, mode='max')
        plot_losses = PlotLosses()
        callbacks_list = [checkpoint, early_stop, plot_losses]

        # TODO: tune optimizer parameters
        vocab_inv = _get_vocabulary_inv(vocab)
        # self._init_weights(domain_name, vocab_inv)
        history = self.model.fit(x_train, y_train, batch_size=batch_size, epochs=num_epochs,
                                 validation_data=(x_test, y_test), verbose=1, callbacks=callbacks_list)

    def load_weights(self, fname):
        self.model.load_weights(fname)


class CNN_DAE(Base_Model):

    def __init__(self):
        model = None

    def create_model(self):
        pass


# successful for image classification
# introduced residual connections
class ResNet101(Base_Model):

    def __init__(self):
        model = None

    def _identity_block(self):
        raise NotImplementedError

    def _convolutional_block(self):
        raise NotImplementedError

    def create_model(self, input_shape=None):
        # TODO: decide on input shape, in case of images (x_dim > 197, y_dim > 197, channels == 3)
        input_shape = input_shape  # _obtain_input_shape(input_shape)

        raise NotImplementedError


class CNN_AE(Base_Model):

    def __init__(self):
        model = None

    def create_model(self, *args):
        pass


class LSTM_AE(Base_Model):

    def __init__(self):
        model = None

    def create_model(self, max_sentence_len, input_dim, latent_dim):
        input_shape = (max_sentence_len, input_dim)
        inputs = Input(shape=input_shape)
        encoded = LSTM(latent_dim)(inputs)

        decoded = RepeatVector(max_sentence_len)()
        decoded = LSTM(input_dim, return_sequences=True)(decoded)

        sequence_autoencoder = Model(inputs, decoded)
        encoder = Model(inputs, encoded)


class CustomVariationalLayer(Layer):
    def __init__(self, z_mean, z_log_var, **kwargs):
        self.is_placeholder = True
        self.z_mean = z_mean
        self.z_log_var = z_log_var

        super(CustomVariationalLayer, self).__init__(**kwargs)

    def vae_loss(self, x, x_decoded_mean, original_dim=3000, latent_dim=1000):
        xent_loss = original_dim * metrics.binary_crossentropy(x, x_decoded_mean)
        kl_loss = -0.5 * k.sum(1 + self.z_log_var - k.square(self.z_mean) - k.exp(self.z_log_var), axis=-1)
        return k.mean(xent_loss + kl_loss)

    def call(self, inputs):
        x = inputs[0]
        x_decoded_mean = inputs[1]
        loss = self.vae_loss(x, x_decoded_mean)
        self.add_loss(loss, inputs=inputs)
        return k.ones_like(x)


# example from keras docs
class VAE(Base_Model):

    def __init__(self):
        self.encoder = None
        self.generator = None
        self.model = None
        self.batch_size = None
        self.latent_dim = None

    # paper: Generating Sentences from a Continuous Space
    def create_simple_model(self, batch_size=500, original_dim=3000, intermediate_dim=1200,
                            latent_dim=1000):
        self.batch_size = batch_size
        self.latent_dim = latent_dim
        x = Input(batch_shape=(batch_size, original_dim))
        h = Dense(intermediate_dim, activation='relu')(x)
        z_mean = Dense(latent_dim)(h)
        z_log_var = Dense(latent_dim)(h)
        z = Lambda(self.sampling, output_shape=(latent_dim,))([z_mean, z_log_var])
        decoder_h = Dense(intermediate_dim, activation='relu')
        decoder_mean = Dense(original_dim, activation='relu')
        h_decoded = decoder_h(z)
        x_decoded_mean = decoder_mean(h_decoded)
        loss_layer = CustomVariationalLayer(z_mean=z_mean,z_log_var=z_log_var)([x, x_decoded_mean])
        vae = Model(x, [loss_layer])
        vae.compile(optimizer='rmsprop', loss=[self.loss])
        self.model = vae

    @staticmethod
    def loss(y_true, y_pred):
        return k.zeros_like(y_pred)

    # dims
    @staticmethod
    def sampling(args):
        z_mean, z_log_var = args
        eps = k.random_normal(shape=(500, 1000), mean=0,
                              stddev=1.0)
        return z_mean + k.exp(z_log_var / 2) * eps

    def train_simple_model(self, x_train, x_test, batch_size=500, num_epochs=200):
        print('Training process has begun')
        checkpoint = ModelCheckpoint('vdcnn_weights.{epoch:03d}-{val_acc:.4f}.hdf5', monitor='val_acc',
                                     verbose=1, save_best_only=True, mode='auto')
        early_stop = EarlyStopping(monitor='val_acc', patience=5, mode='max')
        plot_losses = PlotLosses()
        plot_accuracy = PlotAccuracy()
        callbacks_list = [checkpoint, early_stop, plot_losses, plot_accuracy]

        # self._init_weights(domain_name, vocab_inv)
        history = self.model.fit(x_train, x_train, shuffle=True, batch_size=batch_size, epochs=num_epochs,
                                 validation_data=(x_test, x_test), verbose=1, callbacks=callbacks_list)

    def create_model(self, emb_dim, intermediate_dim=512, batch_size=128,
                     latent_dim=2, epochs=50):
        original_dim = emb_dim * emb_dim
        input_shape = (original_dim,)
        inputs = Input(shape=input_shape, name='emb_input')
        x = Dense(intermediate_dim, activation='relu')(inputs)
        z_mean = Dense(latent_dim, name='z_mean')(x)
        z_log_var = Dense(latent_dim, name='z_log_var')(x)

    # reparametrization trick
    # def sampling(self, z_mean, z_log_var):
    #     batch = k.shape(z_mean)[0]
    #     dim = k.int_shape(z_mean)[1]
    #     eps = k.random_normal(shape=(batch, dim))
    #     return z_mean + k.exp(0.5 * z_log_var) * eps


class VRNN(Base_Model):

    def __init__(self):
        self.model = None

    def create_model(self):
        model = Sequential()
        # encoder
        # decoder
        raise NotImplementedError
        # inputs = Input()

    def _nld_gauss(self, mean_1):
        return


# paper: Very Deep Convolutional Networks for Text Classification, 2016
# http://www.aclweb.org/anthology/E17-1104
class VDCNN(Base_Model):

    def __init__(self):
        self.model = None

    def _identity(self, inputs, filters, kernel_size=3):
        # 'same' padding to preserve dims
        layer_1 = Conv1D(filters=filters, kernel_size=kernel_size, padding='same')(inputs)
        batch_normalization_layer = BatchNormalization()(layer_1)
        activation = Activation('relu')(batch_normalization_layer)
        layer_2 = Conv1D(filters=filters, kernel_size=kernel_size, padding='same')(activation)
        out = BatchNormalization()(layer_2)
        return Activation('relu')(out)

    def _conv_block(self, inputs, filters, pool_type, stage, sorted=True, kernel_size=3):

        layer_1 = Conv1D(filters=filters, kernel_size=kernel_size, padding='same')(inputs)
        batch_norm = BatchNormalization()(layer_1)
        activate = Activation('relu')(batch_norm)
        layer_2 = Conv1D(filters=filters, kernel_size=kernel_size, padding='same')(activate)
        inp = BatchNormalization()(layer_2)

        inp = Activation('relu')(inp)
        inp = self._dim_red(inp, pool_type=pool_type, sorted=sorted, stage=stage)

        inp = Conv1D(filters=2 * filters, kernel_size=1, padding='same', name='1_1_conv_%d' % stage)(inp)
        out = BatchNormalization(name='1_1_batch_normalization_%d' % stage)(inp)
        return out

    def _dim_red(self, inputs, pool_type, sorted, stage):
        if pool_type == 'max':
            out = MaxPooling1D(pool_size=3, strides=2, padding='same', name='pool_%d' % stage)(inputs)
        return out

    # operates at character level
    def create_model(self, sequence_length=512, output_dim=16, num_of_conv_blocks=None, conv_filters=None,
                     pool_type='max', sorted=True, num_classes=5):
        if not num_of_conv_blocks:
            num_of_conv_blocks = [4, 4, 10, 10]
        if not conv_filters:
            conv_filters = [64, 128, 256, 512]

        inputs = Input(shape=(sequence_length,), name='inputs')
        # tensor generation of size (f_0, s)
        char_embedding_layer = Embedding(input_dim=sequence_length, output_dim=output_dim)(inputs)
        inp = Conv1D(filters=64, kernel_size=3, padding='same', name='conv')(char_embedding_layer)
        # stack of temporal convolutional blocks

        # 64
        for _ in range(num_of_conv_blocks[0]):
            # use_bias, shortcut
            inp = self._identity(inputs=inp, filters=conv_filters[0], kernel_size=3)
            inp = self._conv_block(inputs=inp, filters=conv_filters[0], kernel_size=3,
                                   pool_type=pool_type, sorted=sorted, stage=1)

        # 128
        for _ in range(num_of_conv_blocks[1]):
            inp = self._identity(inputs=inp, filters=conv_filters[1], kernel_size=3)
            inp = self._conv_block(inputs=inp, filters=conv_filters[1], kernel_size=3,
                                   pool_type=pool_type, sorted=sorted, stage=2)

        # 256
        for _ in range(num_of_conv_blocks[2]):
            inp = self._identity(inputs=inp, filters=conv_filters[2], kernel_size=3)
            inp = self._conv_block(inputs=inp, filters=conv_filters[2], kernel_size=3,
                                   pool_type=pool_type, sorted=sorted, stage=3)

        # 512
        for _ in range(num_of_conv_blocks[2]):
            inp = self._identity(inputs=inp, filters=conv_filters[3], kernel_size=3)
            inp = self._conv_block(inputs=inp, filters=conv_filters[3], kernel_size=3,
                                   pool_type=pool_type, sorted=sorted, stage=4)

        # maxPooling
        maxPooling_layer = KMaxPooling(k=8, sorted=True)(inp)
        inp = Flatten()(maxPooling_layer)

        # Dense
        inp = Dense(units=2048, activation='relu')(inp)
        inp = Dense(units=2048, activation='relu')(inp)
        out = Dense(units=num_classes, activation='softmax')(inp)

        self.model = Model(inputs=inputs, outputs=out, nalme='VDCNN')
        # TODO: check optimizer validity and params
        print(self.model.summary())
        self.model.compile(optimizer=SGD(lr=0.01, momentum=0.9), loss='categorical_crossentropy', metrics=['accuracy'])
        save_model_to_json(self.model, "vdcnn")

    def train_model(self, x_train, y_train, x_test, y_test, vocab, batch_size=64, num_epochs=100):
        print('Training process has begun')
        checkpoint = ModelCheckpoint('vdcnn_weights.{epoch:03d}-{val_acc:.4f}.hdf5', monitor='val_acc',
                                     verbose=1, save_best_only=True, mode='auto')
        early_stop = EarlyStopping(monitor='val_acc', patience=5, mode='max')
        plot_losses = PlotLosses()
        callbacks_list = [checkpoint, early_stop, plot_losses]

        vocab_inv = _get_vocabulary_inv(vocab)
        # self._init_weights(domain_name, vocab_inv)
        history = self.model.fit(x_train, y_train, batch_size=batch_size, epochs=num_epochs,
                                 validation_data=(x_test, y_test), verbose=1, callbacks=callbacks_list)


# Paper: Deep Pyramid Convolutional Neural Networks for Text Categorization, 2017
class DPCNN(Base_Model):

    def __init__(self):
        self.model = None

    def create_model(self, sequence_length):
        inputs = Input(shape=(sequence_length,), name='inputs')

        raise NotImplementedError


# Paper: Variational autoencoders for collaborative filtering
# Is based on the history of clicks
class MultiDAE(Base_Model):

    def __init__(self):
        self.model = None

    def create_model(self):
        # input =
        raise NotImplementedError


# Collaborative Variational Autoencoder for Recommender Systems
class CVAE(Base_Model):

    def __init__(self):
        self.model = None
