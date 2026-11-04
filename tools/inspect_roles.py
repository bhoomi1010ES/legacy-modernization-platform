import psycopg2

conn = psycopg2.connect("postgresql://postgres:postres123@localhost:5432/rebase")
cur = conn.cursor()

# Check roles table
try:
    cur.execute("SELECT * FROM roles")
    roles = cur.fetchall()
    print("Roles in persistent DB:")
    for r in roles:
        print(r)
except Exception as e:
    print("Error querying roles:", e)

conn.close()

