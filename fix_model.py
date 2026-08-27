with open('models.py', 'r') as f:
    lines = f.readlines()

new_class = '''class PasswordResetToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)

    @staticmethod
    def generate_token():
        return secrets.token_hex(32)

    @classmethod
    def create(cls, user_id, expiry_minutes=30):
        token = cls.generate_token()
        entry = cls(
            user_id=user_id,
            token=token,
            expires_at=datetime.utcnow() + timedelta(minutes=expiry_minutes)
        )
        db.session.add(entry)
        db.session.commit()
        return entry

'''

# Find start and end of PasswordResetToken class
start = None
end = None
for i, line in enumerate(lines):
    if line.startswith('class PasswordResetToken'):
        start = i
    if start and i > start and line.startswith('class '):
        end = i
        break

print(f'Found class at line {start}, ends at line {end}')
new_lines = lines[:start] + [new_class] + lines[end:]
with open('models.py', 'w') as f:
    f.writelines(new_lines)
print('Done')
