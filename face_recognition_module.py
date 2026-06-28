"""
Face Recognition Module
Handles face detection, encoding, training, and recognition
"""

import face_recognition
import cv2
import numpy as np
import pickle
import os
from pathlib import Path
import logging
import threading

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FaceRecognitionSystem:
    """Manages face recognition operations"""
    
    def __init__(self, training_data_path="training_data", model_path="models/face_encodings.pkl"):
        """
        Initialize face recognition system
        
        Args:
            training_data_path: Folder where user face images are stored
            model_path: Path to save/load trained model
        """
        self.training_data_path = Path(training_data_path)
        self.model_path = Path(model_path)
        self.known_face_encodings = []
        self.known_face_names = []
        self.known_face_ids = []
        
        # Create directories if they don't exist
        self.training_data_path.mkdir(exist_ok=True)
        self.model_path.parent.mkdir(exist_ok=True)
        
        # Thread safety lock
        self.lock = threading.Lock()
    
    def capture_face_images(self, user_id, name, num_images=30):
        """
        Capture face images from webcam for training
        
        Args:
            user_id: Unique user identifier
            name: User's name
            num_images: Number of images to capture (default: 30)
        
        Returns:
            bool: True if successful, False otherwise
        """
        # Create user directory
        user_folder = self.training_data_path / user_id
        user_folder.mkdir(exist_ok=True)
        
        # Initialize webcam
        video_capture = cv2.VideoCapture(0)
        
        if not video_capture.isOpened():
            logger.error("Cannot access webcam")
            return False
        
        print(f"\n[INFO] Capturing images for {name}")
        print("> Look at the camera and move your face slightly")
        print("> Press 'q' to cancel\n")
        
        count = 0
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        
        while count < num_images:
            ret, frame = video_capture.read()
            if not ret:
                break
            
            # Convert to grayscale for face detection
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.3, 5)
            
            for (x, y, w, h) in faces:
                # Draw rectangle around face
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                
                # Save face image
                face_img = frame[y:y+h, x:x+w]
                img_path = user_folder / f"{user_id}_{count}.jpg"
                cv2.imwrite(str(img_path), face_img)
                count += 1
                
                # Display progress
                cv2.putText(frame, f"Captured: {count}/{num_images}", (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            
            cv2.imshow('Capturing Face - Press Q to cancel', frame)
            
            # Exit on 'q' key
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        
        video_capture.release()
        cv2.destroyAllWindows()
        
        if count >= 10:  # Minimum 10 images required
            logger.info(f"Captured {count} images for {name}")
            return True
        else:
            logger.error(f"Insufficient images captured ({count})")
            return False
    
    def train_model(self):
        """
        Train the face recognition model using captured images
        Creates face encodings for all users
        
        Returns:
            bool: True if training successful
        """
        print("\n[INFO] Training face recognition model...")
        
        with self.lock:
            self.known_face_encodings = []
            self.known_face_names = []
            self.known_face_ids = []
            
            # Iterate through all user folders
            user_folders = [f for f in self.training_data_path.iterdir() if f.is_dir()]
            
            if not user_folders:
                logger.warning("No training data found")
                return False
            
            for user_folder in user_folders:
                user_id = user_folder.name
                image_files = list(user_folder.glob("*.jpg")) + list(user_folder.glob("*.png"))
                
                if not image_files:
                    continue
                
                print(f"Processing {user_id}...")
                
                # Process each image
                for img_path in image_files:
                    try:
                        # Load image
                        image = face_recognition.load_image_file(str(img_path))
                        
                        # Get face encodings
                        # We use model='hog' (faster) or 'cnn' (more accurate but requires GPU/lots of RAM)
                        # Default is 'hog'
                        encodings = face_recognition.face_encodings(image)
                        
                        if encodings:
                            # Use the first face found
                            encoding = encodings[0]
                            self.known_face_encodings.append(encoding)
                            self.known_face_ids.append(user_id)
                            
                    except Exception as e:
                        logger.warning(f"Error processing {img_path}: {e}")
                        continue
            
            if not self.known_face_encodings:
                logger.error("No faces encoded")
                return False
            
            # Save trained model
            data = {
                'encodings': self.known_face_encodings,
                'ids': self.known_face_ids
            }
            
            try:
                with open(self.model_path, 'wb') as f:
                    pickle.dump(data, f)
                
                logger.info(f"[SUCCESS] Model trained with {len(self.known_face_encodings)} face encodings")
                return True
            except Exception as e:
                logger.error(f"Error saving model: {e}")
                return False
    
    def load_model(self):
        """
        Load trained model from file
        
        Returns:
            bool: True if model loaded successfully
        """
        if not self.model_path.exists():
            logger.warning("No trained model found. Please train the model first.")
            return False
        
        try:
            with open(self.model_path, 'rb') as f:
                data = pickle.load(f)
            
            self.known_face_encodings = data['encodings']
            self.known_face_ids = data['ids']
            
            logger.info(f"[SUCCESS] Model loaded with {len(self.known_face_encodings)} encodings")
            return True
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            return False
    
    def recognize_face(self, frame):
        """
        Recognize faces in a video frame
        
        Args:
            frame: Video frame (numpy array)
        
        Returns:
            tuple: (annotated_frame, list of (user_id, name, location))
        """
        # Resize frame for faster processing
        small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
        rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
        
        # Find faces and encodings in current frame
        # Use a non-blocking check for the lock to avoid freezing the video feed during training
        if self.lock.locked():
            return []

        with self.lock:
            face_locations = face_recognition.face_locations(rgb_small_frame)
            face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)
        
        recognized_faces = []
        
        for face_encoding, face_location in zip(face_encodings, face_locations):
            # Compare with known faces
            matches = face_recognition.compare_faces(
                self.known_face_encodings, 
                face_encoding,
                tolerance=0.6  # Lower = more strict
            )
            
            user_id = "Unknown"
            confidence = 0
            
            # Find best match
            if True in matches:
                face_distances = face_recognition.face_distance(
                    self.known_face_encodings, 
                    face_encoding
                )
                best_match_index = np.argmin(face_distances)
                
                if matches[best_match_index]:
                    user_id = self.known_face_ids[best_match_index]
                    confidence = 1 - face_distances[best_match_index]
            
            # Scale back face location
            top, right, bottom, left = face_location
            top *= 4
            right *= 4
            bottom *= 4
            left *= 4
            
            recognized_faces.append({
                'user_id': user_id,
                'confidence': confidence,
                'location': (top, right, bottom, left)
            })
        
        return recognized_faces
    
    def draw_face_boxes(self, frame, recognized_faces, user_names=None):
        """
        Draw bounding boxes and names on detected faces
        
        Args:
            frame: Video frame
            recognized_faces: List of recognized face data
            user_names: Dictionary mapping user_id to name
        
        Returns:
            Annotated frame
        """
        if user_names is None:
            user_names = {}
        
        for face in recognized_faces:
            user_id = face['user_id']
            confidence = face['confidence']
            top, right, bottom, left = face['location']
            
            # Choose color based on recognition
            if user_id == "Unknown":
                color = (0, 0, 255)  # Red for unknown
                label = "Unknown"
            else:
                color = (0, 255, 0)  # Green for recognized
                name = user_names.get(user_id, user_id)
                label = f"{name} ({confidence*100:.1f}%)"
            
            # Draw rectangle
            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
            
            # Draw label background
            cv2.rectangle(frame, (left, bottom - 35), (right, bottom), color, cv2.FILLED)
            
            # Draw label text
            cv2.putText(frame, label, (left + 6, bottom - 6),
                       cv2.FONT_HERSHEY_DUPLEX, 0.6, (255, 255, 255), 1)
        
        return frame