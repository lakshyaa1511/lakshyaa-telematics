with open('app.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if '    device_id = data.get("device_id") or None' in line and i == 994:
        lines[i] = '        device_id = data.get("device_id") or None\n'
        print(f'Fixed line {i+1}')

with open('app.py', 'w') as f:
    f.writelines(lines)
print('Done')
