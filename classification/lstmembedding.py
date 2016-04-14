import numpy as np
from keras.utils import np_utils

from sklearn.cross_validation import train_test_split
from keras.models import Sequential
from keras.layers.recurrent import LSTM
from keras.layers.core import Dropout, Dense
import json
from keras.callbacks import EarlyStopping
from classification.LossHistoryVisualization import LossHistoryVisualisation
from keras.layers.embeddings import Embedding

def train_and_evaluate_lstm_with_embedding(config, X_train, X_test, y_train, y_test, output_dim, task, vocab, vector_by_token, vector_by_code):
    y_train = np_utils.to_categorical(y_train, output_dim)
    y_test = np_utils.to_categorical(y_test, output_dim)
    
    
    X_train, X_validation, y_train, y_validation = train_test_split(X_train, y_train, test_size=0.15, random_state=23)
    
    n_symbols = len(vocab)
    embedding_weights = np.zeros((n_symbols, config['word2vec-dim-size']), dtype=np.float32)
    for index, word in enumerate(vocab):
        # skip first item 'mask'
        if index == 0 or word == '':
            continue
        embedding_weights[index,:] = vector_by_token[word] if config['use-all-tokens-in-embedding'] or word not in vector_by_code else vector_by_code[word]
       
    model = Sequential()
    model.add(Embedding(n_symbols, config['word2vec-dim-size'], input_length=config['maxlen'], mask_zero=True, weights=[embedding_weights]))
    for i, layer in enumerate(config['lstm-layers']):
        model.add(LSTM(output_dim=layer['output-size'], activation=config['lstm-activation'], 
                       inner_activation=config['lstm-inner-activation'], init=config['lstm-init'],
                       inner_init=config['lstm-inner-init'],  return_sequences=i != len(config['lstm-layers']) - 1))
        model.add(Dropout(layer['dropout']))
    
    model.add(Dense(output_dim, activation='softmax', init=config['outlayer-init']))
    
    model.compile(loss='categorical_crossentropy',
                  optimizer=config['optimizer'],
                  metrics=['accuracy'])
    
    json.dump(json.loads(model.to_json()), 
              open(config['base_folder'] + 'classification/model_lstm_' + task + '.json','w'), indent=4, sort_keys=True)   

    
    early_stopping = EarlyStopping(monitor='val_acc', patience=10)
    visualizer = LossHistoryVisualisation(config['base_folder'] + 'classification/epochs_' + task + '.png')
    model.fit(X_train, y_train,
              nb_epoch=50,
              batch_size=64,
              validation_data=(X_validation, y_validation),
              verbose=2,
              callbacks=[early_stopping, visualizer])
    
    print("Prediction using LSTM..")
    score = model.evaluate(X_test, y_test, verbose=0)
    print('Test score:', score[0])
    print('Test accuracy:', score[1])  

    return [model, score[1]]
