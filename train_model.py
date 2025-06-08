import cv2
import numpy as np
import mysql.connector
import os

# Initialize MySQL database connection
db_connection = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",  # Enter your MySQL password
    database="Thesis"  # Enter your database name
)
cursor = db_connection.cursor()

# Initialize the face recognizer
recognizer = cv2.face.LBPHFaceRecognizer.create()

# Path to the directory to store the model
model_dir = 'models'
if not os.path.exists(model_dir):
    os.makedirs(model_dir)
model_path = os.path.join(model_dir, 'face_recognizer.yml')

def get_images_and_labels():
    cursor.execute("SELECT user_id, Picture FROM Log")
    rows = cursor.fetchall()

    face_samples = []
    ids = []

    for row in rows:
        user_id, picture = row
        photo_data = np.frombuffer(picture, np.uint8)
        img = cv2.imdecode(photo_data, cv2.IMREAD_GRAYSCALE)

        if img is None:
            print(f"Warning: Could not decode image for user_id {user_id}")
            continue

        face_samples.append(img)
        ids.append(user_id)

    return face_samples, ids

def train_model():
    faces, ids = get_images_and_labels()
    if len(faces) == 0 or len(ids) == 0:
        print("No face data found. Ensure the database contains valid images.")
        return

    print(f"Number of faces: {len(faces)}")
    print(f"Number of IDs: {len(ids)}")
    print(f"Face sample shapes: {[face.shape for face in faces]}")
    print(f"IDs: {ids}")

    recognizer.train(faces, np.array(ids))
    recognizer.save(model_path)
    print(f"Model trained and saved at {model_path}")

if __name__ == '__main__':
    train_model()


