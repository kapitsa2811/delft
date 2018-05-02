import os

import numpy as np
import datetime

from textClassification.config import ModelConfig, TrainingConfig
from textClassification.models import getModel
from textClassification.models import train_model
from textClassification.models import train_folds
from textClassification.models import train_test_split
from textClassification.models import predict
from textClassification.models import predict_folds
from textClassification.preprocess import prepare_preprocessor, TextPreprocessor

from sklearn.metrics import log_loss, roc_auc_score, accuracy_score, f1_score

from utilities.Embeddings import filter_embeddings

class Classifier(object):

    config_file = 'config.json'
    weight_file = 'model_weights.hdf5'
    preprocessor_file = 'preprocessor.pkl'

    def __init__(self, 
                 model_name="",
                 model_type="gru",
                 list_classes=[],
                 char_emb_size=25, 
                 word_emb_size=300, 
                 dropout=0.5, 
                 use_char_feature=False, 
                 batch_size=256, 
                 optimizer='adam', 
                 learning_rate=0.001, 
                 lr_decay=0.9,
                 clip_gradients=5.0, 
                 max_epoch=50, 
                 patience=5,
                 log_dir=None,
                 maxlen=300,
                 fold_number=1,
                 use_roc_auc=True,
                 embeddings=()):

        self.model_config = ModelConfig(model_name, model_type, list_classes, 
                                        char_emb_size, word_emb_size, dropout, 
                                        use_char_feature, maxlen, fold_number)
        self.training_config = TrainingConfig(batch_size, optimizer, learning_rate,
                                              lr_decay, clip_gradients, max_epoch,
                                              patience, use_roc_auc)
        self.model = None
        self.models = None
        self.p = None
        self.log_dir = log_dir
        self.embeddings = embeddings 

    def train(self, x_train, y_train, vocab_init=None):
        self.p = prepare_preprocessor(x_train, vocab_init)

        embeddings = filter_embeddings(self.embeddings, self.p.vocab_word,
                                       self.model_config.word_embedding_size)

        x_train = self.p.to_sequence(x_train, self.model_config.maxlen)

        # create validation set in case we don't use k-folds
        xtr, val_x, y, val_y = train_test_split(x_train, y_train, test_size=0.1)

        self.model = getModel(self.model_config.model_type, embeddings, len(self.model_config.list_classes))
        self.model, best_roc_auc = train_model(self.model, self.model_config.list_classes, self.training_config.batch_size, 
            self.training_config.max_epoch, self.training_config.use_roc_auc, xtr, y, val_x, val_y)


    def train_nfold(self, x_train, y_train, vocab_init=None):

        self.p = prepare_preprocessor(x_train, vocab_init=vocab_init)

        embeddings = filter_embeddings(self.embeddings, self.p.vocab_word,
                                       self.model_config.word_embedding_size)

        xtr = self.p.to_sequence(x_train, self.model_config.maxlen)

        self.models = train_folds(xtr, y_train, self.model_config.fold_number, self.model_config.list_classes, self.training_config.batch_size, 
            self.training_config.max_epoch, self.model_config.model_type, self.training_config.use_roc_auc, embeddings)


    # classification
    def predict(self, texts, output_format='json'):
        if self.model_config.fold_number is 1:
            if self.model is not None:
                #classifier = Classifier(self.model, preprocessor=self.p)
                x_t = self.p.to_sequence(texts, maxlen=300)
                result = predict(self.model, x_t)
            else:
                raise (OSError('Could not find a model.'))
        else:
            if self.models is not None:
                x_t = self.p.to_sequence(texts, maxlen=300)
                result = predict_folds(self.models, x_t)
            else:
                raise (OSError('Could not find nfolds models.'))
        if output_format is 'json':
            res = {
                "software": "DeLFT",
                "date": datetime.datetime.now().isoformat(),
                "model": self.model_config.model_name,
                "classifications": []
            }
            i = 0
            for text in texts:
                classification = {
                    "text": text
                }
                the_res = result[i]
                j = 0
                for cl in self.model_config.list_classes:
                    classification[cl] = float(the_res[j])
                    j += 1
                res["classifications"].append(classification)
                i += 1
            return res
        else:
            return result

    def eval(self, x_test, y_test):
        if self.model_config.fold_number is 1:
            if self.model is not None:
                x_t = self.p.to_sequence(x_test, maxlen=300)
                result = predict(self.model, x_t)
            else:
                raise (OSError('Could not find a model.'))
        else:
            if self.models is not None:
                x_t = self.p.to_sequence(x_test, maxlen=300)
                result = predict_folds(self.models, x_t)
            else:
                raise (OSError('Could not find nfolds models.'))
        print("-----------------------------------------------")
        print("\nEvaluation on", x_test.shape[0], "instances:")

        total_accuracy = 0.0
        total_f1 = 0.0
        total_loss = 0.0
        total_roc_auc = 0.0

        def normer(t):
            if t < 0.5: 
                return 0 
            else: 
                return 1
        vfunc = np.vectorize(normer)
        result_binary = vfunc(result)
        
        # macro-average (average of class scores)
        # we distinguish 1-class and multiclass problems 
        if len(self.model_config.list_classes) is 1:
            total_accuracy = accuracy_score(y_test, result_binary)
            total_f1 = f1_score(y_test, result_binary)
            total_loss = log_loss(y_test, result)
            total_roc_auc = roc_auc_score(y_test, result)
        else:
            for j in range(0, len(self.model_config.list_classes)):
                accuracy = accuracy_score(y_test[:, j], result_binary[:, j])
                total_accuracy += accuracy
                f1 = f1_score(y_test[:, j], result_binary[:, j], average='micro')
                total_f1 += f1
                loss = log_loss(y_test[:, j], result[:, j])
                total_loss += loss
                roc_auc = roc_auc_score(y_test[:, j], result[:, j])
                total_roc_auc += roc_auc
                print("\nClass:", self.model_config.list_classes[j])
                print("\taccuracy at 0.5 =", accuracy)
                print("\tf-1 at 0.5 =", f1)
                print("\tlog-loss =", loss)
                print("\troc auc =", roc_auc)

        total_accuracy /= len(self.model_config.list_classes)
        total_f1 /= len(self.model_config.list_classes)
        total_loss /= len(self.model_config.list_classes)
        total_roc_auc /= len(self.model_config.list_classes)

        print("\nMacro-average:")
        print("\taverage accuracy at 0.5 =", total_accuracy)
        print("\taverage f-1 at 0.5 =", total_f1)
        print("\taverage log-loss =", total_loss)
        print("\taverage roc auc =", total_roc_auc)

        total_accuracy = 0.0
        total_f1 = 0.0
        total_loss = 0.0
        total_roc_auc = 0.0

        # micro-average (average of scores for each instance)
        for i in range(0, result.shape[0]):
            #for j in range(0, len(self.model_config.list_classes)):
            accuracy = accuracy_score(y_test[i,:], result_binary[i,:])
            total_accuracy += accuracy
            f1 = f1_score(y_test[i,:], result_binary[i,:], average='micro')
            total_f1 += f1
            loss = log_loss(y_test[i,:], result[i,:])
            total_loss += loss
            roc_auc = roc_auc_score(y_test[i,:], result[i,:])
            total_roc_auc += roc_auc

        total_accuracy /= result.shape[0]
        total_f1 /= result.shape[0]
        total_loss /= result.shape[0]
        total_roc_auc /= result.shape[0]

        print("\nMicro-average:")
        print("\taverage accuracy at 0.5 =", total_accuracy)
        print("\taverage f-1 at 0.5 =", total_f1)
        print("\taverage log-loss =", total_loss)
        print("\taverage roc auc =", total_roc_auc)


    def save(self, dir_path='data/models/textClassification/'):
        # create subfolder for the model if not already exists
        directory = os.path.join(dir_path, self.model_config.model_name)
        if not os.path.exists(directory):
            os.makedirs(directory)
        
        self.p.save(os.path.join(directory, self.preprocessor_file))
        print('preprocessor saved')
        
        self.model_config.save(os.path.join(directory, self.config_file))
        print('model config file saved')
        
        if self.model_config.fold_number is 1:
            if self.model is not None:
                self.model.save(os.path.join(directory, self.model_config.model_type+"."+self.weight_file))
                print('model saved')
            else:
                print('Error: model has not been built')
        else:
            if self.models is None:
                print('Error: nfolds models have not been built')
            else:
                for i in range(0, self.model_config.fold_number):
                    self.models[i].save(os.path.join(directory, self.model_config.model_type+".model{0}_weights.hdf5".format(i)))
                print('nfolds model saved')

    def load(self, dir_path='data/models/textClassification/'):
        self.p = TextPreprocessor.load(os.path.join(dir_path, self.model_config.model_name, self.preprocessor_file))
        
        self.model_config = ModelConfig.load(os.path.join(dir_path, self.model_config.model_name, self.config_file))
        
        dummy_embeddings = np.zeros((len(self.p.word_index())+1, self.model_config.word_embedding_size), dtype=np.float32)
        self.model = getModel(self.model_config.model_type, dummy_embeddings,len(self.model_config.list_classes))
        if self.model_config.fold_number is 1:
            self.model.load_weights(os.path.join(dir_path, self.model_config.model_name, self.model_config.model_type+"."+self.weight_file))
        else:
            self.models = []
            for i in range(0, self.model_config.fold_number):
                local_model = getModel(self.model_config.model_type, dummy_embeddings, len(self.model_config.list_classes))
                local_model.load_weights(os.path.join(dir_path, self.model_config.model_name, self.model_config.model_type+".model{0}_weights.hdf5".format(i)))
                self.models.append(local_model)


