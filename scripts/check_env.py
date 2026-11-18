from sqlcipher3 import dbapi2 as sqlcipher

conn = sqlcipher.connect(":memory:")
conn.execute("PRAGMA key='test-key'")
print("cipher_version:", conn.execute("PRAGMA cipher_version").fetchone())
print("sqlite_version:", conn.execute("select sqlite_version()").fetchone())
conn.execute("create table t (id integer primary key, v text)")
conn.execute("insert into t (v) values ('secret')")
conn.commit()
print("row:", conn.execute("select v from t").fetchone())
conn.close()
