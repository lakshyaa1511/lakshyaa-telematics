with open('models.py', 'r') as f:
    lines = f.readlines()

# Find second class Trip
found = 0
start = None
for i, line in enumerate(lines):
    if 'class Trip(db.Model):' in line:
        found += 1
        if found == 2:
            start = i
            break

if start:
    # Remove from second Trip class to next class or EOF
    end = start + 1
    while end < len(lines) and not lines[end].startswith('class '):
        end += 1
    del lines[start:end]
    with open('models.py', 'w') as f:
        f.writelines(lines)
    print(f'Removed duplicate Trip class (lines {start+1} to {end})')
else:
    print('No duplicate found')
