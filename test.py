import mysql.connector
import cv2
import numpy as np
import tensorflow as tf
from numpy import genfromtxt
import pandas as pd
import tensorflow as tf
from tensorflow.python.keras.models import Sequential
from tensorflow.python.keras.layers import Conv2D, ZeroPadding2D, Activation, Input, concatenate
from tensorflow.python.keras.models import Model
from tensorflow.python.keras.layers.normalization import BatchNormalization
from tensorflow.python.keras.layers.pooling import MaxPooling2D, AveragePooling2D
from tensorflow.python.keras.layers.merge import Concatenate
from tensorflow.python.keras.layers.core import Lambda, Flatten, Dense
from tensorflow.python.keras.initializers import glorot_uniform
from tensorflow.python.keras.engine.topology import Layer
from keras import backend as K
K.set_image_data_format('channels_first')
import cv2
import os
import numpy as np
from numpy import genfromtxt
import pandas as pd
import tensorflow as tf
from fr_utils import *
from inception_blocks_v2 import *
from keras import backend as K


K.set_image_data_format('channels_first')
np.set_printoptions(threshold=np.nan)

FRmodel = faceRecoModel(input_shape=(3, 96, 96))
print("Total Params:", FRmodel.count_params())

def triplet_loss(y_true, y_pred, alpha=0.2):
    anchor, positive, negative = y_pred[0], y_pred[1], y_pred[2]
    pos_dist = tf.reduce_sum(tf.square(anchor - positive), axis=-1)
    neg_dist = tf.reduce_sum(tf.square(anchor - negative), axis=-1)
    basic_loss = pos_dist - neg_dist + alpha
    loss = tf.reduce_sum(tf.maximum(basic_loss, 0.0))
    return loss

FRmodel.compile(optimizer='adam', loss=triplet_loss, metrics=['accuracy'])
load_weights_from_FaceNet(FRmodel)

def connect_to_db():
    connection = mysql.connector.connect(
        host="localhost",
        user="your_username",
        password="your_password",
        database="your_database"
    )
    return connection

def get_users_from_db():
    connection = connect_to_db()
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT * FROM your_table_name")
    users = cursor.fetchall()
    cursor.close()
    connection.close()
    return users

def blob_to_image(blob):
    np_arr = np.frombuffer(blob, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    return img

def create_database(users):
    database = {}
    for user in users:
        first_name = user['First_Name']
        last_name = user['Last_Name']
        name = f"{first_name} {last_name}"
        img = blob_to_image(user['Picture'])
        img_path = f"images/{name}.jpg"
        cv2.imwrite(img_path, img)
        database[name] = img_to_encoding(img_path, FRmodel)
    return database

users = get_users_from_db()
database = create_database(users)

def verify(image_path, identity, database, model):
    encoding = img_to_encoding(image_path, model)
    dist = np.linalg.norm(encoding - database[identity])
    if dist < 0.7:
        print(f"It's {identity}, welcome in!")
        return dist, True
    else:
        print(f"It's not {identity}, please go away")
        return dist, False

def who_is_it(image_path, database, model):
    encoding = img_to_encoding(image_path, model)
    min_dist = 100
    identity = None

    for (name, db_enc) in database.items():
        dist = np.linalg.norm(encoding - db_enc)
        if dist < min_dist:
            min_dist = dist
            identity = name

    if min_dist > 0.7:
        print("Not in the database.")
        return min_dist, None
    else:
        print(f"It's {identity}, the distance is {min_dist}")
        return min_dist, identity

# Verify identity
verify("images/camera_0.jpg", "Person Name", database, FRmodel)

# Recognize the person in the image
who_is_it("images/camera_0.jpg", database, FRmodel)



