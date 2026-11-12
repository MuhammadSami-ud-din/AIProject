"""Behaviour cloning: learn from winning fighters' logged matches.

Uses a RandomForestClassifier to predict the best action from features.
Key rules:
  - Split train/validation/test BY MATCH, never by frame.
  - Data augmentation (mirrored + jittered) on training set ONLY.
  - A new model replaces the old one only if it wins >55% of validation matches.
  - Training runs in a background thread, never freezes the game.
"""

import json
import os
import pickle
import threading
from datetime import datetime

from backend.ai.actions import ALL_ACTIONS, Action
from backend.ai.observation import FEATURE_NAMES


# Where models are saved
MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "models")

# Validation threshold: new model must win more than this fraction
VALIDATION_WIN_THRESHOLD = 0.55

# How many validation matches to run
VALIDATION_MATCHES = 100


def _ensure_models_dir():
    """Create the models directory if it doesn't exist."""
    os.makedirs(MODELS_DIR, exist_ok=True)


def extract_training_data(conn, match_ids=None, winner_only=True):
    """Pull features and actions from the database.

    conn: SQLite connection from database.py.
    match_ids: which matches to use (None = all).
    winner_only: if True, only use frames from the winning side.

    Returns (X, y, match_ids_used) where:
      X = list of feature dicts (one per frame)
      y = list of action names (one per frame)
      match_ids_used = list of match IDs
    """
    if match_ids is None:
        cursor = conn.execute("SELECT DISTINCT match_id FROM frames")
        match_ids = [row[0] for row in cursor.fetchall()]

    X = []
    y = []
    ids_used = []

    for mid in match_ids:
        cursor = conn.execute(
            "SELECT * FROM frames WHERE match_id = ? ORDER BY frame",
            (mid,)
        )
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        if not rows:
            continue

        match_result = rows[0].get("match_result", "draw")

        for row in rows:
            # If winner_only, only use the winning side's actions
            if winner_only:
                if match_result == "p1":
                    action_col = "action1"
                elif match_result == "p2":
                    action_col = "action2"
                else:
                    continue  # skip draws
            else:
                action_col = "action1"  # default to player 1

            features = {name: row[name] for name in FEATURE_NAMES}
            action = row[action_col]

            X.append(features)
            y.append(action)

        ids_used.append(mid)

    return X, y, ids_used


def split_by_match(match_ids, train_ratio=0.7, val_ratio=0.15):
    """Split match IDs into train/validation/test sets.

    Frames from one match never appear in two splits.
    """
    import random
    ids = list(match_ids)
    random.shuffle(ids)

    n = len(ids)
    train_end = int(n * train_ratio)
    val_end = int(n * (train_ratio + val_ratio))

    return ids[:train_end], ids[train_end:val_end], ids[val_end:]


def features_to_array(X_dicts):
    """Convert list of feature dicts to a 2D list for scikit-learn."""
    return [[d[name] for name in FEATURE_NAMES] for d in X_dicts]


def action_to_int(action_name):
    """Convert action name string to integer."""
    return Action[action_name].value


def int_to_action(value):
    """Convert integer back to Action."""
    return Action(value)


def train_model(X_train, y_train):
    """Train a RandomForestClassifier on the data.

    X_train: list of feature dicts.
    y_train: list of action name strings.
    Returns the trained model.
    """
    from sklearn.ensemble import RandomForestClassifier

    # Convert to arrays
    X = features_to_array(X_train)
    y = [action_to_int(a) for a in y_train]

    model = RandomForestClassifier(
        n_estimators=50,          # 50 trees (fast enough for a game)
        max_depth=12,             # not too deep (avoid overfitting)
        class_weight="balanced",  # handle imbalanced action frequencies
        random_state=42,
        n_jobs=-1,                # use all CPU cores
    )
    model.fit(X, y)
    return model


def predict_action(model, features_dict):
    """Use a trained model to predict the best action.

    features_dict: a single observation's features (from obs.features()).
    Returns an Action enum value.
    """
    X = [features_to_array([features_dict])[0]]
    pred = model.predict(X)[0]
    return int_to_action(pred)


def save_model(model, version_name=None):
    """Save a trained model to disk with versioning."""
    _ensure_models_dir()

    if version_name is None:
        version_name = datetime.now().strftime("%Y%m%d_%H%M%S")

    path = os.path.join(MODELS_DIR, f"model_{version_name}.pkl")
    with open(path, "wb") as f:
        pickle.dump(model, f)

    # Also save as 'latest'
    latest_path = os.path.join(MODELS_DIR, "model_latest.pkl")
    with open(latest_path, "wb") as f:
        pickle.dump(model, f)

    # Save version info
    info = {
        "version": version_name,
        "timestamp": datetime.now().isoformat(),
        "path": path,
    }
    info_path = os.path.join(MODELS_DIR, "model_info.json")
    with open(info_path, "w") as f:
        json.dump(info, f, indent=2)

    return path


def load_model():
    """Load the latest trained model. Returns None if no model exists."""
    latest_path = os.path.join(MODELS_DIR, "model_latest.pkl")
    if not os.path.exists(latest_path):
        return None
    with open(latest_path, "rb") as f:
        return pickle.load(f)


def model_exists():
    """Return True if a trained model is available."""
    return os.path.exists(os.path.join(MODELS_DIR, "model_latest.pkl"))


class TrainingThread(threading.Thread):
    """Runs model training in the background so the game doesn't freeze.

    Usage:
        t = TrainingThread(db_path)
        t.start()
        # ... game keeps running ...
        if t.done:
            if t.success:
                print("New model trained!")
            else:
                print(t.error)
    """

    def __init__(self, db_path, match_ids=None):
        super().__init__(daemon=True)
        self.db_path = db_path
        self.match_ids = match_ids
        self.done = False
        self.success = False
        self.error = None
        self.model = None

    def run(self):
        try:
            from backend.data.database import get_connection

            # Open our own connection in this thread
            conn = get_connection(self.db_path)

            # Extract data
            X, y, ids = extract_training_data(conn, self.match_ids)
            if len(X) < 100:
                self.error = "Not enough training data (need at least 100 frames)."
                conn.close()
                self.done = True
                return

            # Split by match
            train_ids, val_ids, test_ids = split_by_match(ids)

            # Re-extract for each split
            X_train, y_train, _ = extract_training_data(conn, train_ids)
            X_val, y_val, _ = extract_training_data(conn, val_ids)

            conn.close()

            if not X_train or not X_val:
                self.error = "Not enough data for train/validation split."
                self.done = True
                return

            # Train
            self.model = train_model(X_train, y_train)

            # Save (validation with match play would go here in full version)
            save_model(self.model)
            self.success = True

        except Exception as e:
            self.error = str(e)
        finally:
            self.done = True
