with open('app.py', 'r') as f:
    content = f.read()

old = '        return render_template("profile.html", user=user)\n@app.route("/integrations/traccar/link"'
new = '    return render_template("profile.html", user=user)\n@app.route("/integrations/traccar/link"'

if old in content:
    content = content.replace(old, new)
    with open('app.py', 'w') as f:
        f.write(content)
    print('Fixed!')
else:
    print('Pattern not found - checking...')
    # find the line
    for i, line in enumerate(content.split('\n')):
        if 'return render_template("profile.html"' in line:
            print(f'Line {i+1}: [{line}]')
