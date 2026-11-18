import sys
sys.path.insert(0, r"C:\Users\Giridhar.R\Memosphere")
from memosphere.db.__init__ import init_db, DB_PATH
print("DB_PATH:", DB_PATH)
init_db()
print("DB initialized successfully")