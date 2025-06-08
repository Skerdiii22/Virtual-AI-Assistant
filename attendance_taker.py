import cv2
import numpy as np
import mysql.connector
from datetime import datetime, timedelta
from shapely.geometry import Point, Polygon
import pandas as pd
import logging
import os
from skimage.metrics import structural_similarity as ssim
from cv2 import data

# Set environment variable to skip OpenCV AVFoundation authorization
os.environ["OPENCV_AVFOUNDATION_SKIP_AUTH"] = "1"

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Load the pre-trained face detection model
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

# Ensure you have installed opencv-contrib-python
recognizer = cv2.face.LBPHFaceRecognizer_create()
model_path = 'models/face_recognizer.yml'
if os.path.exists(model_path):
    recognizer.read(model_path)
else:
    logging.error("Face recognition model not found. Please train the model first.")
    raise FileNotFoundError("Face recognition model not found. Please train the model first.")

# Initialize MySQL database connection
db_connection = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",  # Enter your MySQL password
    database="Thesis"  # Enter your database name
)
cursor = db_connection.cursor()

# Load timetable from CSV file
timetable = pd.read_csv("timetable.csv")

def get_current_course():
    now = datetime.now()
    current_time = now.strftime("%H:%M")
    current_day = now.strftime("%A")

    logging.debug(f"Looking for current course at time {current_time} on {current_day}")
    for index, row in timetable.iterrows():
        if row['Day'] == current_day:
            for time_slot in ['09:00 - 11:00', '11:00 - 13:00', '13:00 - 15:00']:
                try:
                    start_time, end_time = time_slot.split(' - ')
                    start_time = start_time.strip()
                    end_time = end_time.strip()
                    if start_time <= current_time <= end_time:
                        course = row[time_slot]
                        if pd.notna(course):
                            logging.debug(f"Found current course: {course}")
                            return course, start_time
                except ValueError as e:
                    logging.error(f"Error parsing time slot '{time_slot}': {e}")
    logging.debug(f"No course found for current time {current_time} on {current_day}")
    return None, None

def record_attendance(user_id, course):
    now = datetime.now()
    time = now.strftime('%Y-%m-%d %H:%M:%S')

    try:
        cursor.execute("INSERT INTO Attendance (user_id, time, course) VALUES (%s, %s, %s)",
                       (user_id, time, course))
        db_connection.commit()
        logging.debug(f"Recorded attendance for user_id {user_id} in course {course} at {time}")
    except mysql.connector.Error as err:
        logging.error(f"Error recording attendance: {err}")

def get_user_photo(user_id):
    try:
        cursor.execute("SELECT Picture FROM Log WHERE user_id = %s", (user_id,))
        result = cursor.fetchone()
        if result:
            photo_data = result[0]
            return np.frombuffer(photo_data, np.uint8)
        else:
            logging.debug(f"No photo found for user_id {user_id}")
            return None
    except mysql.connector.Error as err:
        logging.error(f"Error retrieving user photo: {err}")
        return None

def is_user_within_rectangle(user_coords, rectangle_coords):
    polygon = Polygon(rectangle_coords)
    point = Point(user_coords)
    is_within = polygon.contains(point)
    logging.debug(f"User coordinates {user_coords} within rectangle: {is_within}")
    return is_within

rectangle_coords = [
    (41.35, 19.78),         # Top-left (Northwest)
    (41.35, 19.8842004),    # Top-right (Northeast)
    (41.30, 19.8842004),    # Bottom-right (Southeast)
    (41.30, 19.78),         # Bottom-left (Southwest)
    (41.35, 19.78)          # Closing the rectangle (same as top-left)
]


def compare_images(img1, img2):
    try:
        s = ssim(img1, img2)
        logging.debug(f"SSIM: {s}")
        return s > 0.4  # Adjust threshold as needed
    except Exception as e:
        logging.error(f"Error during image comparison: {e}")
        return False

def take_attendance(latitude, longitude, user_id):
    user_id = user_id
    current_class, start_time_str = get_current_course()
    if current_class and start_time_str:
        start_time = datetime.strptime(start_time_str, "%H:%M").replace(year=datetime.now().year, month=datetime.now().month, day=datetime.now().day)
        attendance_end_time = start_time + timedelta(minutes=110)
        now = datetime.now()

        logging.debug(f"Class start time: {start_time_str}, Attendance window end time: {attendance_end_time.strftime('%H:%M')}")
        if start_time <= now <= attendance_end_time:
            cap = None
            try:
                cap = cv2.VideoCapture(0)
                if not cap.isOpened():
                    logging.error("Failed to initialize the webcam. Exiting...")
                    return {"error": "Failed to initialize the webcam"}

                while True:
                    ret, frame = cap.read()
                    if not ret:
                        logging.error("Failed to capture frame from webcam. Exiting...")
                        break

                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(30, 30))
                    logging.debug(f"Faces detected: {faces}")

                    if len(faces) == 0:
                        logging.debug("No faces detected.")
                        continue

                    for (x, y, w, h) in faces:
                        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                        roi_gray = gray[y:y + h, x:x + w]
                        try:
                            logging.debug(f"Predicting face at position {(x, y, w, h)} with ROI shape: {roi_gray.shape}")
                            id_, confidence = recognizer.predict(roi_gray)
                            logging.debug(f"Detected face with id {id_} and confidence {confidence}")
                        except cv2.error as e:
                            logging.error(f"OpenCV error during face prediction: {e}")
                            continue
                        except Exception as e:
                            logging.error(f"General error during face prediction: {e}")
                            continue

                        if confidence < 130:
                            user_id = id_
                            photo = get_user_photo(user_id)
                            if photo is not None:
                                try:
                                    user_img = cv2.imdecode(photo, cv2.IMREAD_COLOR)
                                    if user_img is None:
                                        logging.error("Failed to decode user image")
                                        continue

                                    user_img_gray = cv2.cvtColor(user_img, cv2.COLOR_BGR2GRAY)
                                    user_img_gray_resized = cv2.resize(user_img_gray, (w, h))

                                    # Save images for visual inspection
                                    cv2.imwrite('detected_roi.png', roi_gray)
                                    cv2.imwrite('user_img_gray.png', user_img_gray)
                                    cv2.imwrite('user_img_gray_resized.png', user_img_gray_resized)

                                    # Normalize images
                                    roi_gray_normalized = cv2.equalizeHist(roi_gray)
                                    user_img_gray_resized_normalized = cv2.equalizeHist(user_img_gray_resized)

                                    # Log shapes and comparison
                                    logging.debug(f"Detected ROI shape: {roi_gray.shape}, User image shape: {user_img_gray.shape}, Resized user image shape: {user_img_gray_resized.shape}")
                                    logging.debug(f"Detected ROI mean: {roi_gray.mean()}, Resized user image mean: {user_img_gray_resized.mean()}")
                                    logging.debug(f"Normalized ROI mean: {roi_gray_normalized.mean()}, Normalized resized user image mean: {user_img_gray_resized_normalized.mean()}")

                                    # Compare images using SSIM
                                    if compare_images(roi_gray_normalized, user_img_gray_resized_normalized):
                                        user_coords = (latitude, longitude)
                                        if is_user_within_rectangle(user_coords, rectangle_coords):
                                            logging.debug("User is within the attendance area")
                                            course = current_class
                                            record_attendance(user_id, course)
                                            cap.release()
                                            cv2.destroyAllWindows()
                                            return {"success": "Attendance taken successfully"}
                                        else:
                                            logging.debug("User is not within the attendance area")
                                    else:
                                        logging.debug("Face does not match with the user's photo")
                                except cv2.error as e:
                                    logging.error(f"OpenCV error during photo processing: {e}")
                                except Exception as e:
                                    logging.error(f"General error during photo processing: {e}")
                            else:
                                logging.debug("User's photo not found")
                        else:
                            logging.debug("Face not recognized")

                    cv2.imshow('Frame', frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break

            except Exception as e:
                logging.error(f"Error in take_attendance: {e}")
                return {"error": f"Error in take_attendance: {e}"}
            finally:
                if cap is not None and cap.isOpened():
                    cap.release()
                cv2.destroyAllWindows()
        else:
            logging.debug("Current time is outside the attendance window.")
            return {"error": "Current time is outside the attendance window."}
    else:
        logging.debug("No current class found for attendance.")
        return {"error": "No current class found for attendance."}




