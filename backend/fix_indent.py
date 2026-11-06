with open('backend/app/services/sandbox_client.py', 'r', encoding='utf-8') as f:
    text = f.read()

bad = '                files = dict(execution.get("files", {}))'
good = '        files = dict(execution.get("files", {}))'
assert bad in text, 'bad not found'
text = text.replace(bad, good)
with open('backend/app/services/sandbox_client.py', 'w', encoding='utf-8') as f:
    f.write(text)
print('Fixed indentation in sandbox_client.py')

