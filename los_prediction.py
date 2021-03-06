from tokenization.tokenize_codes import tokenize_catalogs
import os
from subprocess import call
import json
from json import encoder
from sklearn.cross_validation import train_test_split
import numpy as np

from classification.evaluation import plot_histogram
from classification.lstmembedding import train_and_evaluate_lstm_with_embedding
from load_config import load_config
from reader.sequence.pcreadersequence import SequencePCReader
import keras.preprocessing.sequence

from sklearn.externals import joblib

encoder.FLOAT_REPR = lambda o: format(o, '.8f')

from vectorize import read_code_vectors, read_vectors, create_word2vec_training_data

def calculate_drg_baseline(y_train, y_test, drgs_train, drgs_test):
    averages_by_drg = {}
    global_average = y_train.mean()
    for i in range(0, y_train.shape[0]):
        drg = drgs_train[i]
        if not drg in averages_by_drg:
            averages_by_drg[drg] = []
        averages_by_drg[drg].append(y_train[i])
    for drg in averages_by_drg:
        averages_by_drg[drg] = np.mean(np.array(averages_by_drg[drg]))
    
    predictions = np.zeros(y_test.shape[0])
    for i in range(0, y_test.shape[0]):
        drg = drgs_test[i]
        predictions[i] = averages_by_drg[drg] if drg in averages_by_drg else global_average
    
    
    error = y_test - global_average
    mse = np.square(error).mean()
    mape = np.abs(error / y_test).mean()
    mae = np.abs(error).mean()

    print('Global average LOS: ' + str(global_average))
    print('Total test MAPE global average baseline: ' + str(mape))
    print('Total test MSE global average baseline: ' + str(mse))
    print('Total test MAE global average baseline: ' + str(mae))
    
    error = predictions - y_test
    mse = np.square(error).mean()
    mape = np.abs(error / y_test).mean()
    mae = np.abs(error).mean()

    print('Total test MAPE DRG baseline: ' + str(mape))
    print('Total test MSE DRG baseline: ' + str(mse))
    print('Total test MAE DRG baseline: ' + str(mae))
    


def run (config):
    base_folder = config['base_folder']
    
    if config["only-fr-descriptions"] + config["only-it-descriptions"] + config["only-de-fr-descriptions"] + config["only-de-it-descriptions"] + config["only-fr-it-descriptions"] + config["only-de-fr-it-descriptions"] > 1:
        print("You can't select more than one language option.")
        return   
    
    if not config['skip-word2vec']:
        print("Tokenize catalogs..")
        if not os.path.exists(base_folder + 'tokenization'):
            os.makedirs(base_folder + 'tokenization')
        tokenize_catalogs(config)
        
        print("Vectorize catalogs..")
        if not os.path.exists(base_folder + 'vectorization'):
            os.makedirs(base_folder + 'vectorization')
        word2vec_trainset = config['all-tokens']
        if config['use-training-data-for-word2vec']:
            create_word2vec_training_data(config['training-set-word2vec'], config['all-tokens'], 
                                          base_folder + 'vectorization/train.txt',
                                          do_shuffle=config['shuffle-word2vec-traindata'],
                                          use_n_times=config['num-shuffles'],
                                          use_demographic_tokens=config['use_demographic_tokens'])
            word2vec_trainset = base_folder + 'vectorization/train.txt'
        call(["word2vec", "-train", word2vec_trainset, "-binary",
               "0", "-cbow", '1' if config['word2vec-cbow'] else '0', "-output", config['all-vectors'],
                "-size", str(config['word2vec-dim-size']), "-save-vocab",
                config['word2vec-vocab'], "-min-count", "1", "-threads", str(config['num-cores'])])
    
    print("\nRead vectors. Assign vectors to codes..")
    # one vector for each token in the vocabulary
    vector_by_token = read_vectors(config['all-vectors'])
    vocab = vector_by_token.keys()
    
    if config['store-everything']:
        json.dump({k: v.tolist() for k, v in vector_by_token.items()}, open(config['all-vectors'] + '.json','w'), indent=4, sort_keys=True)

    res = read_code_vectors(vector_by_token, config['all-tokens'])
    
    # for each code a list of vectors of its tokens
    vectors_by_code = res['vectors']
    # for each code a list of its tokens
    tokens_by_code = res['tokens']
    # for each code a vector that is the normalized sum of all vectors from all tokens from this code.
    vector_by_code = res['vector_by_code']
    
    if config['store-everything']:
        json.dump({k: v.tolist() for k, v in vectors_by_code.items()}, open(config['code-vectors'],'w'), sort_keys=True)
        json.dump(tokens_by_code, open(config['code-tokens'],'w'), indent=4, sort_keys=True)
    
    if not os.path.exists(base_folder + 'classification'):
        os.makedirs(base_folder + 'classification')
    
    reader = SequencePCReader(config['training-set'])
    reader.tokens_by_code = tokens_by_code
    reader.vocab = vocab
    reader.use_demographic_tokens = config['use_demographic_tokens']
    reader.use_all_tokens = config['use-all-tokens-in-embedding']

    reader.read_from_file(vectors_by_code, 'los', drg_out_file=config['training-set-drgs'], demo_variables_to_use=config['demo-variables'])
    codes = reader.data
    targets = reader.targets
    demo_data = reader.demo_data
    drgs = reader.drgs
    y = np.zeros(len(codes), dtype=np.float32)
    for i, target in enumerate(targets):
        y[i] = target

    codes_train, codes_test, demo_train, demo_test, y_train, y_test, drgs_train, drgs_test = train_test_split(codes, demo_data, y, drgs, test_size=0.33, random_state=42)
    calculate_drg_baseline(y_train, y_test, drgs_train, drgs_test)
    output_dim = 1
           
    print("Training data dimensionality: " + str(len(codes)) + " | " + str(len(codes[0])))
    print('Train LSTM Neural Net with Embedding..')
    vocab = reader.vocab
    codes_train = keras.preprocessing.sequence.pad_sequences(codes_train, maxlen=config['maxlen'], dtype='int', truncating='pre')
    codes_test = keras.preprocessing.sequence.pad_sequences(codes_test, maxlen=config['maxlen'], dtype='int', truncating='pre')
                 
    model, _ = train_and_evaluate_lstm_with_embedding(config, codes_train, codes_test, demo_train, demo_test, y_train, y_test, output_dim, 'los', vocab, 
                                                                  vector_by_token,
                                                                  vector_by_code)


    predictions = model.predict({'codes_input':codes_test, 'demo_input':demo_test}, verbose=0)
   
    error = predictions[:,0] - y_test
    
    plot_histogram(config, y_test, 'ACTUAL_LOS')
    plot_histogram(config, predictions[:,0], 'PREDICTED_LOS')
    plot_histogram(config, error, 'ERROR')
    
    mse = np.square(error).mean()
    mape = np.abs(error / y_test).mean()
    mae = np.abs(error).mean()

    if config['store-everything']:
        joblib.dump(model, base_folder + 'classification/' + config['classifier'] + '.pkl')
    
    print('Total test MAPE: ' + str(mape))
    print('Total test MSE: ' + str(mse))
    print('Total test MAE: ' + str(mae))
    return mse
    
    
if __name__ == '__main__':
    config = load_config()
    base_folder = config['base_folder']
    
    
    if not os.path.exists(base_folder):
        os.makedirs(base_folder)
    
    json.dump(config, open(base_folder + 'configuration-los.json','w'), indent=4, sort_keys=True)    
    
    run(config)
    