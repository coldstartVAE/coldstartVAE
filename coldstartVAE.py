from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from keras.layers import Lambda, Input, Dense, concatenate 
from keras.models import Model
from keras.datasets import mnist
from keras.losses import mse, binary_crossentropy
from keras import backend as K
from keras.regularizers import l2
from keras.callbacks import Callback

from tensorflow.python.ops import nn
import tensorflow as tf

import numpy as np
import argparse
import os
import random
from math import log

from sklearn.model_selection import train_test_split
from scipy.spatial import distance
from sklearn.svm import LinearSVC
from sklearn.metrics import f1_score, precision_score, recall_score 

# dataset
movies = np.load("npy/movies.npy")
books = np.load("npy/books.npy")

test_users = 3500

def unison_shuffled_copies(a, b):
    assert len(a) == len(b)
    p = np.random.permutation(len(a))
    return a[p], b[p]

movies, books = unison_shuffled_copies(movies, books)

movies1 = movies[:movies.shape[0]-test_users,:]
movies2 = movies[movies.shape[0]-test_users:,:]

books1 = books[:movies.shape[0]-test_users,:]
books2 = books[movies.shape[0]-test_users:,:]

# network parameters
original_dim = movies.shape[1]
original_dim2 = books.shape[1] 
layer1_dim = 512
layer2_dim = 256 
latent_dim = 128    

print("network", original_dim, original_dim2, layer1_dim, layer2_dim, latent_dim)

batch_size = 128    
epochs = 40
decay = 1e-4 
bias = True
hadamard = 10  

print("params", batch_size, epochs, decay, hadamard)

print("books: ", books.shape[0], books.shape[1])
print("movie: ", movies.shape[0], movies.shape[1])
print("books non zero:", np.count_nonzero(books))

print("books1: ", books1.shape[0], books1.shape[1])
print("books2: ", books2.shape[0], books2.shape[1])
print("movie1: ", movies1.shape[0], movies1.shape[1])
print("movie2: ", movies2.shape[0], movies2.shape[1])

#evaluation protocal
eval_items = list()
userc = 0
for user in range(books.shape[0] - test_users, books.shape[0]):
    nonzero = np.nonzero(books[user])
    for item in nonzero[0]:
        eval_items.append(str(userc) + "_" + str(item))

    userc += 1

r = random.SystemRandom()

print("books non zero:", np.count_nonzero(books), len(eval_items))

# reparameterization trick
# instead of sampling from Q(z|X), sample eps = N(0,I)
# z = z_mean + sqrt(var)*eps
def sampling(args):
    z_mean, z_log_var = args
    batch = K.shape(z_mean)[0]
    dim = K.int_shape(z_mean)[1]
    # by default, random_normal has mean=0 and std=1.0
    epsilon = K.random_normal(shape=(batch, dim))
    return z_mean + K.exp(0.5 * z_log_var) * epsilon

def normalize(d):
    # d is a (n x dimension) np array
    d -= np.min(d, axis=0)
    d /= np.ptp(d, axis=0)
    return d

#neural nets
input_shape = (original_dim, )
input_shape2 = (original_dim2, )

# VAE model = encoder + decoder
# build encoder model
#for s
inputs_s = Input(shape=input_shape, name='encoder_s1_input')
se1 = Dense(layer1_dim, kernel_regularizer=l2(decay), bias_regularizer=l2(decay), use_bias=bias, activation='tanh')(inputs_s)
se2 = Dense(layer2_dim, kernel_regularizer=l2(decay), bias_regularizer=l2(decay), use_bias=bias, activation='tanh')(se1)

z_mean_s = Dense(latent_dim, kernel_regularizer=l2(decay), bias_regularizer=l2(decay), use_bias=bias, name='z_mean_s')(se2)
z_log_var_s = Dense(latent_dim,  kernel_regularizer=l2(decay), bias_regularizer=l2(decay), use_bias=bias, name='z_log_var_s')(se2)

# use reparameterization trick to push the sampling out as input
# note that "output_shape" isn't necessary with the TensorFlow backend
z_s = Lambda(sampling, output_shape=(latent_dim,), name='z_s')([z_mean_s, z_log_var_s])

z_si = Dense(latent_dim, kernel_regularizer=l2(decay), bias_regularizer=l2(decay), use_bias=bias, activation='tanh', name='z_si')(z_s)

#for i
inputs_i = Input(shape=input_shape2, name='encoder_i_input')
ie1 = Dense(layer1_dim, kernel_regularizer=l2(decay), bias_regularizer=l2(decay), use_bias=bias, activation='tanh')(inputs_i)
ie2 = Dense(layer2_dim, kernel_regularizer=l2(decay), bias_regularizer=l2(decay), use_bias=bias, activation='tanh')(ie1)

z_mean_i = Dense(latent_dim, kernel_regularizer=l2(decay), bias_regularizer=l2(decay), use_bias=bias, name='z_mean_i')(ie2)
z_log_var_i = Dense(latent_dim,  kernel_regularizer=l2(decay), bias_regularizer=l2(decay), use_bias=bias, name='z_log_var_i')(ie2)

# use reparameterization trick to push the sampling out as input
# note that "output_shape" isn't necessary with the TensorFlow backend
z_i = Lambda(sampling, output_shape=(latent_dim,), name='z_i')([z_mean_i, z_log_var_i])

# instantiate encoder model
encoder_s = Model([inputs_s], [z_mean_s, z_log_var_s, z_s, z_si], name='encoder_s')
encoder_s.summary()
encoder_i = Model([inputs_i], [z_mean_i, z_log_var_i, z_i], name='encoder_i')
encoder_i.summary()

# build decoder model
latent_inputs_s = Input(shape=(latent_dim,), name='z_samplings')
sd2 = Dense(layer2_dim, kernel_regularizer=l2(decay), bias_regularizer=l2(decay), use_bias=bias, activation='tanh')(latent_inputs_s)
sd1 = Dense(layer1_dim, kernel_regularizer=l2(decay), bias_regularizer=l2(decay), use_bias=bias, activation='tanh')(sd2)
outputs_s = Dense(original_dim, activation='sigmoid')(sd1)

latent_inputs_i = Input(shape=(latent_dim,), name='z_samplingi')
id2 = Dense(layer2_dim, kernel_regularizer=l2(decay), bias_regularizer=l2(decay), use_bias=bias, activation='tanh')(latent_inputs_i)
id1 = Dense(layer1_dim, kernel_regularizer=l2(decay), bias_regularizer=l2(decay), use_bias=bias, activation='tanh')(id2)
outputs_i = Dense(original_dim2, activation='sigmoid')(id1)

# instantiate decoder model
decoder_s = Model(latent_inputs_s, outputs_s, name='decoder_s')
decoder_s.summary()

decoder_i = Model(latent_inputs_i, outputs_i, name='decoder_i')
decoder_i.summary()

# instantiate VAE model
outputs_s = decoder_s(encoder_s([inputs_s])[2])
outputs_i = decoder_i(encoder_s([inputs_s])[3])

vae = Model([inputs_s, inputs_i], [outputs_s, outputs_i], name='vae_mlp')
vae.summary()

vae_prediction = Model(inputs_s, outputs_i, name='vae_pred')
vae_prediction.summary()

class Histories(Callback):
    def on_epoch_end(self, epoch, logs={}):
        print("predictions starting")
        predictions_i = vae_prediction.predict([movies2], batch_size=batch_size)
        
        user_ranks = list()

        for txt in range(len(eval_items)):

            tokens = eval_items[txt].split("_") 
            user = int(tokens[0])
            item = int(tokens[1])

            comp_values = list()
            comp_keys = list()
        
            zerovals = np.where(books[user] == 0)[0]

            while True:
                randint = r.randint(0, len(zerovals) - 1)
        
                if zerovals[randint] not in comp_keys:
                    comp_values.append(predictions_i[user, zerovals[randint]])
                    comp_keys.append(zerovals[randint])
        
                if len(comp_keys) == 99:
                    break
        
            #do ranking 
            comp_value = predictions_i[user, item]
        
            rank = [i for i in comp_values if i >= comp_value] 
            rank = len(rank) #+ 1
            user_ranks.append(rank)
        
        evranks = [5, 10, 20, 50]        
        for rank in evranks:
        
            HR = (sum(vv <  rank for vv in user_ranks)/float(len(user_ranks)))

            MRR = 0.0
            for val in user_ranks:
                if val < rank:
                    MRR += (1/float(val + 1))
            MRR = MRR/float(len(user_ranks))
        
            NDCG = 0.0
            for val in user_ranks:
                if val < rank:
                    NDCG += log(2) / log(val + 2)
                    #DCG += (1/float(log((val), 2)))
            NDCG = NDCG/float(len(user_ranks))
        
            print("Epoch ", epoch, "HR NDCG MRR at ", rank, " :", HR, NDCG, MRR)

        return

def custom_crossentropy(inputs, outputs, hadamard):
    #for sig-moid only
    e1 = K.mean(K.binary_crossentropy(inputs, outputs), axis=-1) 
    outputs = outputs*inputs
    e2 = K.mean(K.binary_crossentropy(inputs, outputs), axis=-1) 
    return (e1 + hadamard*e2) 

if __name__ == '__main__':

    reconstruction_loss_s = custom_crossentropy(inputs_s, outputs_s, hadamard)
    reconstruction_loss_s *= original_dim

    reconstruction_loss_i = custom_crossentropy(inputs_i, outputs_i, hadamard)
    reconstruction_loss_i *= original_dim2

    kl_loss_s = 1 + z_log_var_s - K.square(z_mean_s) - K.exp(z_log_var_s)
    kl_loss_s = K.sum(kl_loss_s, axis=-1)
    kl_loss_s *= -0.5

    kl_loss_i = 1 + z_log_var_i - K.square(z_mean_i) - K.exp(z_log_var_i)
    kl_loss_i = K.sum(kl_loss_i, axis=-1)
    kl_loss_i *= -0.5

    custom_loss = mse(z_si, z_i)
    custom_loss *= latent_dim 
 

    vae_loss = K.mean((reconstruction_loss_s + reconstruction_loss_i) + (kl_loss_s + kl_loss_i) + custom_loss)
    vae.add_loss(vae_loss)
    vae.compile(optimizer='adam')
    vae.summary()

    # prepare callback
    histories = Histories()

    vae.fit([movies1, books1], epochs=epochs, batch_size=batch_size, shuffle=True, callbacks=[histories])


