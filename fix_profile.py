with open('app.py', 'r') as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    lineno = i + 1
    if 1357 <= lineno <= 1387:
        # Fix: remove 4 extra spaces from these lines
        if line.startswith('            '):
            line = line[4:]
    new_lines.append(line)

with open('app.py', 'w') as f:
    f.writelines(new_lines)
print('Done')
