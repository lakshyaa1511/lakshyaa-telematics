with open('models.py', 'r') as f:
    content = f.read()

old = '    device = db.relationship("Device", backref="trips")        db.session.add(entry)\n        db.session.commit()\n        return entry'
new = '    device = db.relationship("Device", backref="trips")'

content = content.replace(old, new)
with open('models.py', 'w') as f:
    f.write(content)
print('Done')
