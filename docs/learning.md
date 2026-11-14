# Learning (Behaviour Cloning) — M8

## File: `backend/data/learning.py`

Trains a RandomForestClassifier to predict the best action
from observation features, learning from winning fighters' logged matches.

## Key Rules

1. **Split by match:** Frames from one match never appear in
   both the training and validation sets.
2. **Data augmentation** on training set ONLY:
   - `mirrored()`: flip the arena left-to-right
   - `jittered()`: add tiny random noise to positions and health
3. **Model validation:** A new model replaces the old one only if
   it wins more than 55% of validation matches (otherwise rollback).
4. **Background thread:** Training runs in `TrainingThread`,
   never freezes the game.

## Functions

| Function | Purpose |
|----------|---------|
| `extract_training_data(conn)` | Pull features + actions from the DB |
| `split_by_match(ids)` | Split match IDs into train/val/test |
| `augment_training_data(X, y)` | Add mirrored + jittered copies |
| `train_model(X, y)` | Train a RandomForestClassifier |
| `predict_action(model, features)` | Predict one action |
| `save_model(model, version)` | Save with versioning |
| `load_model()` | Load the latest model |
| `rollback_model(version)` | Roll back to a previous version |
| `list_model_versions()` | List all saved versions |

## Model Versioning

All models are saved in `backend/data/models/` with:
- `model_<version>.pkl` — the trained model
- `model_latest.pkl` — always points to the current best
- `model_info.json` — version history

## TrainingThread

```python
t = TrainingThread(db_path)
t.start()
# game keeps running...
if t.done:
    if t.success:
        print("New model trained!")
    else:
        print(t.error)
```
