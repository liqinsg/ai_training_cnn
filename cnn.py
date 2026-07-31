import tensorflow as tf
from tensorflow.keras import layers, models

# 1. Initialize a sequential model framework
model = models.Sequential()

# 2. Add Convolutional and Pooling Layers (Feature Extraction)
# Processes a 64x64 RGB image (3 color channels)
model.add(layers.Input(shape=(64, 64, 3))) 
model.add(layers.Conv2D(32, (3, 3), activation='relu'))
model.add(layers.MaxPooling2D((2, 2)))

model.add(layers.Conv2D(64, (3, 3), activation='relu'))
model.add(layers.MaxPooling2D((2, 2)))

# 3. Add Dense Layers (Classification)
model.add(layers.Flatten())
model.add(layers.Dense(64, activation='relu'))
model.add(layers.Dense(10, activation='softmax')) # 10 output classes

# 4. Compile the Model
model.compile(optimizer='adam',
              loss='sparse_categorical_crossentropy',
              metrics=['accuracy'])

# Print architecture summary
model.summary()
