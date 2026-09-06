# Empty on purpose: its presence makes pytest add the project root to
# sys.path so tests can `import parser`, `import db`, etc. despite the flat
# (non-package) layout.
