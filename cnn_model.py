import os
import glob
import tensorflow as tf
from tensorflow.keras import layers, models

# =========================
# Config
# =========================
DATA_DIR = "data/train/iscsi"   # <- contains iscsi.png
IMAGE_SIZE = (64, 64)
BATCH_SIZE = 1
EPOCHS = 5
SEED = 42  # kept for future use

NUM_CLASSES = 1  # single class

# =========================
# Load image file paths
# =========================
image_paths = sorted(
    glob.glob(os.path.join(DATA_DIR, "*.png")) +
    glob.glob(os.path.join(DATA_DIR, "*.jpg")) +
    glob.glob(os.path.join(DATA_DIR, "*.jpeg")) +
    glob.glob(os.path.join(DATA_DIR, "*.bmp")) +
    glob.glob(os.path.join(DATA_DIR, "*.gif"))
)

if len(image_paths) == 0:
    raise FileNotFoundError(f"No images found in {DATA_DIR}")

# =========================
# Train/val split (safe for tiny datasets)
# =========================
# With 1 image, you’ll end up with either 1 train / 0 val, or 0 train / 1 val.
# We force: if only 1 image, keep it in training and make val empty.
if len(image_paths) == 1:
    train_paths = image_paths
    val_paths = []
else:
    split = int(0.8 * len(image_paths))
    train_paths = image_paths[:split]
    val_paths = image_paths[split:]

def make_ds(paths):
    paths_ds = tf.data.Dataset.from_tensor_slices(paths)

    def load_one(path):
        img_bytes = tf.io.read_file(path)
        img = tf.io.decode_image(img_bytes, channels=3, expand_animations=False)
        img = tf.image.resize(img, IMAGE_SIZE)
        img = tf.cast(img, tf.float32) / 255.0
        label = tf.constant(0, dtype=tf.int32)
        return img, label

    ds = paths_ds.map(load_one, num_parallel_calls=tf.data.AUTOTUNE)

    # If empty, still return a valid dataset (Keras may reject empty val).
    ds = ds.batch(BATCH_SIZE).prefetch(tf.data.AUTOTUNE)
    return ds

train_ds = make_ds(train_paths)
val_ds = make_ds(val_paths) if len(val_paths) > 0 else None

print(f"Found {len(image_paths)} images total.")
print(f"Train: {len(train_paths)} | Val: {len(val_paths)} | NUM_CLASSES={NUM_CLASSES}")

# =========================
# Model
# =========================
model = models.Sequential([
    layers.Input(shape=(IMAGE_SIZE[0], IMAGE_SIZE[1], 3)),

    layers.Conv2D(32, 3, padding="same", activation="relu"),
    layers.MaxPooling2D(2),

    layers.Conv2D(64, 3, padding="same", activation="relu"),
    layers.MaxPooling2D(2),

    layers.Conv2D(128, 3, padding="same", activation="relu"),
    layers.MaxPooling2D(2),

    layers.GlobalAveragePooling2D(),
    layers.Dropout(0.3),

    layers.Dense(64, activation="relu"),
    layers.Dropout(0.3),

    layers.Dense(NUM_CLASSES, activation="softmax")
])

model.summary()

model.compile(
    optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3),
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"]
)

# =========================
# Train
# =========================
callbacks = [
    tf.keras.callbacks.ReduceLROnPlateau(monitor="loss", factor=0.5, patience=1)
]

if val_ds is None:
    history = model.fit(
        train_ds,
        epochs=EPOCHS,
        callbacks=callbacks
    )
else:
    history = model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=EPOCHS,
        callbacks=callbacks
    )

# model.save("cnn_model.h5")
model.save("cnn_model.keras")
print("Model saved to cnn_model.h5")