#from sequenceLabelling.reader import batch_iter
from sequenceLabelling.data_generator import DataGenerator
from keras.optimizers import Adam
from sequenceLabelling.metrics import get_callbacks
import numpy as np
np.random.seed(7)
# seed is fixed for reproducibility

class Trainer(object):

    def __init__(self,
                 model,
                 models,
                 model_config,
                 training_config,
                 checkpoint_path='',
                 save_path='',
                 preprocessor=None,
                 embeddings=(),
                 ):

        # for single model training
        self.model = model

        # for n-folds training
        self.models = models

        self.model_config = model_config
        self.training_config = training_config
        self.checkpoint_path = checkpoint_path
        self.save_path = save_path
        self.preprocessor = preprocessor
        self.embeddings = embeddings


    """ train the instance self.model """
    def train(self, x_train, y_train, x_valid, y_valid):
        self.model.summary()
        self.model.compile(loss=self.model.crf.loss,
                           optimizer=Adam(lr=self.training_config.learning_rate))
        #self.model.compile(loss='binary_crossentropy', 
        #                    optimizer='adam', metrics=['accuracy'])
        self.model = self.train_model(self.model, x_train, y_train, x_valid, y_valid, 
                                                  self.training_config.max_epoch)

    """ parameter model local_model must be compiled before calling this method 
        this model will be returned with trained weights """
    def train_model(self, local_model, x_train, y_train, x_valid=None, y_valid=None, max_epoch=50):
        # todo: if valid set if None, create it as random segment of the shuffled train set 

        training_generator = DataGenerator(x_train, y_train, 
            batch_size=self.training_config.batch_size, preprocessor=self.preprocessor, 
            word_embed_size=self.model_config.word_embedding_size, 
            char_embed_size=self.model_config.char_embedding_size, 
            embeddings=self.embeddings, shuffle=True)

        validation_generator = DataGenerator(x_valid, y_valid,  
            batch_size=self.training_config.batch_size, preprocessor=self.preprocessor, 
            word_embed_size=self.model_config.word_embedding_size, 
            char_embed_size=self.model_config.char_embedding_size, 
            embeddings=self.embeddings, shuffle=False)

        callbacks = get_callbacks(log_dir=self.checkpoint_path,
                                  eary_stopping=True,
                                  valid=(validation_generator, self.preprocessor))

        local_model.fit_generator(generator=training_generator,
                                    epochs=max_epoch,
                                    use_multiprocessing=True,
                                    workers=6,
                                    callbacks=callbacks)

        return local_model

    """ n-fold training for the instance model 
        the n models are stored in self.models, and self.model is left untrained  """
    def train_nfold(self, x_train, y_train, fold_count):
        fold_count = len(models)
        fold_size = len(x_train) // fold_count
        #roc_scores = []
        
        for fold_id in range(0, fold_count):
            print('\n------------------------ fold ' + str(fold_id) + '--------------------------------------')

            fold_start = fold_size * fold_id
            fold_end = fold_start + fold_size

            if fold_id == fold_size - 1:
                fold_end = len(x_train)

            train_x = np.concatenate([x_train[:fold_start], x_train[fold_end:]])
            train_y = np.concatenate([y_train[:fold_start], y_train[fold_end:]])

            val_x = x_train[fold_start:fold_end]
            val_y = y_train[fold_start:fold_end]

            foldModel = models[fold_id]

            foldModel.summary()
            foldModel.compile(loss=self.model.crf.loss,
                           optimizer=Adam(lr=self.training_config.learning_rate))

            foldModel = train_model(foldModel, 
                                    self.training_config.batch_size, 
                                    max_epoch, 
                                    train_x, 
                                    train_y, 
                                    val_x, 
                                    val_y)
            self.models.append(foldModel)

