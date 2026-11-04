import psycopg2

conn = psycopg2.connect("postgresql://postgres:postres123@localhost:5432/rebase")
cur = conn.cursor()

def get_columns(table_name):
    cur.execute(
        "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = %s ORDER BY ordinal_position",
        (table_name,),
    )
    return cur.fetchall()

print("MODULES columns:", get_columns("modules"))
print("\nMODULE_ATTEMPTS columns:", get_columns("module_attempts"))
print("\nWORKFLOW_OUTBOX columns:", get_columns("workflow_outbox"))
print("\nWORKFLOW_GATES columns:", get_columns("workflow_gates"))
print("\nJOBS columns:", get_columns("jobs"))

conn.close()

