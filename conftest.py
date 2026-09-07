# Empty on purpose: its presence makes pytest add the project root to
# sys.path so tests can `from backend import db`, `from scripts.sync_places
# import ...`, etc.
