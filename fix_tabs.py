with open('app.py', 'r') as f:
    content = f.read()

# Replace tabs with 4 spaces
content = content.expandtabs(4)

with open('app.py', 'w') as f:
    f.write(content)
print('Done')
